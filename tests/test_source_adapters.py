"""
Tests for the upstream source adapters (the anti-corruption layer, AGENTS.md section 2).

The adapters are tested against the real pinned payloads under tools/fixtures/upstream/real/.
Tests whose names start with `test_synthetic_` use a small hand-built dict for an edge case the
real captures do not contain. Their docstrings say so; they never stand in for real data.
"""

import ast
import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import source_adapters
from tools.source_adapters import (
    CLINVAR_CONFLICTING,
    REVIEW_STATUS_STARS,
    AdapterError,
    PayloadIntegrityError,
    TruncatedSearch,
    UpstreamSnapshot,
    check_clinvar_search_complete,
    esearch_uids,
    gnomad_variant_ids_from_dbsnp,
    is_multiple_variants_refusal,
    load_pinned,
    parse_dbsnp,
    parse_gnomad_constraint,
    parse_gnomad_variant,
    parse_vep,
    select_clinvar_record,
    verify_pinned_payloads,
)
from tools.variome_models import normalize_edit

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "tools" / "fixtures" / "upstream" / "real"
CURATION = json.loads((ROOT / "tools" / "curation" / "kb_curation.json").read_text(encoding="utf-8"))
LOCI = CURATION["loci"]

# Written out independently of the curation file. SPDI positions are 0-based (reports/t2-allele-table.md);
# the indel is dbSNP's TCTT>T, whose VCF anchor sits one base to the left.
SPDI_POSITIONS = {
    "rs113993960": (117199644, 117559590),
    "rs1799945": (26091178, 26090950),
    "rs1799963": (46761054, 46739504),
    "rs1800562": (26093140, 26092912),
    "rs1801133": (11856377, 11796320),
    "rs3918290": (97915613, 97450057),
    "rs4149056": (21331548, 21178614),
    "rs4244285": (96541615, 94781858),
    "rs429358": (45411940, 44908683),
    "rs4988235": (136608645, 135851075),
    "rs6025": (169519048, 169549810),
    "rs671": (112241765, 111803961),
    "rs7412": (45412078, 44908821),
    "rs9923231": (31107688, 31096367),
}
# ClinVar record for each locus: constraints L2 / reports/task-2-code-report.md accession table.
CLINVAR_EXPECTED = {
    "rs113993960": ("VCV000007105", "practice guideline", 4),
    "rs1799945": ("VCV000000010", CLINVAR_CONFLICTING, 1),
    "rs1799963": ("VCV000013310", "criteria provided, multiple submitters, no conflicts", 2),
    "rs1800562": ("VCV000000009", "criteria provided, multiple submitters, no conflicts", 2),
    "rs1801133": ("VCV000003520", "reviewed by expert panel", 3),
    "rs3918290": ("VCV000000432", "reviewed by expert panel", 3),
    "rs4149056": ("VCV000037346", "reviewed by expert panel", 3),
    "rs4244285": ("VCV000633856", "practice guideline", 4),
    "rs429358": ("VCV000017864", CLINVAR_CONFLICTING, 1),
    "rs4988235": ("VCV000007685", "no assertion criteria provided", 0),
    "rs6025": ("VCV000000642", "reviewed by expert panel", 3),
    "rs671": ("VCV000018390", "reviewed by expert panel", 3),
    "rs7412": ("VCV000017848", "reviewed by expert panel", 3),
    "rs9923231": ("VCV000002211", "reviewed by expert panel", 3),
}
# MANE Select RefSeq transcript per locus (from the pinned VEP payloads).
MANE_REFSEQ = {
    "rs113993960": "NM_000492.4", "rs1799945": "NM_000410.4", "rs1799963": "NM_000506.5",
    "rs1800562": "NM_000410.4", "rs1801133": "NM_005957.5", "rs3918290": "NM_000110.4",
    "rs4149056": "NM_006446.5", "rs4244285": "NM_000769.4", "rs429358": "NM_000041.4",
    "rs4988235": "NM_005915.6", "rs6025": "NM_000130.5", "rs671": "NM_000690.4",
    "rs7412": "NM_000041.4", "rs9923231": "NM_024006.6",
}
ALL_RSIDS = sorted(SPDI_POSITIONS)


@pytest.fixture(scope="module")
def snapshot():
    return UpstreamSnapshot(REAL)


def read(source, key):
    return json.loads((REAL / source / f"{key}.json").read_text(encoding="utf-8"))


def locus_args(rsid):
    locus = LOCI[rsid]
    return locus["pos_grch38"], locus["ref"], locus["alt"]


# ---------------------------------------------------------------------------
# ClinVar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rsid", ALL_RSIDS)
def test_clinvar_selects_the_record_for_the_locus_alleles(snapshot, rsid):
    accession, status, stars = CLINVAR_EXPECTED[rsid]
    record = snapshot.clinvar(rsid, *locus_args(rsid))
    assert record is not None
    assert record.accession == accession
    assert record.review_status == status
    assert record.stars == stars
    assert record.conflicting is (status == CLINVAR_CONFLICTING)
    assert record.accession_version.startswith(accession + ".")
    assert record.provenance.accession == record.accession_version


def test_clinvar_rs6025_skips_the_lrrk2_record_and_the_reference_allele_record(snapshot):
    """CR-4 / L3: rs6025's search also returns LRRK2 VCV001940 and a ref-allele record VCV000226007."""
    record = snapshot.clinvar("rs6025", *locus_args("rs6025"))
    assert record.accession == "VCV000000642"
    assert "F5" in record.title


def test_clinvar_rs4244285_takes_the_star_allele_record_not_the_likely_benign_snv(snapshot):
    """The single-variant c.681G>A record says 'Likely benign'; the *2 haplotype record is the defining one."""
    record = snapshot.clinvar("rs4244285", *locus_args("rs4244285"))
    assert record.obj_type == "Haplotype" and record.title == "CYP2C19*2"
    assert record.significance == "drug response"
    assert "star-allele" in record.selected_by


def test_clinvar_rs429358_takes_the_single_variant_record_over_haplotypes(snapshot):
    record = snapshot.clinvar("rs429358", *locus_args("rs429358"))
    assert record.obj_type == "single nucleotide variant"
    assert record.significance == "Conflicting classifications of pathogenicity; other; risk factor"


def test_clinvar_rs3918290_matches_the_alt_allele_not_the_other_record_at_the_position(snapshot):
    """Two records share this rsid: C>G (VCV002429124) and C>T (VCV000000432). The locus alt is T."""
    assert snapshot.clinvar("rs3918290", 97450058, "C", "T").accession == "VCV000000432"
    assert snapshot.clinvar("rs3918290", 97450058, "C", "G").accession == "VCV002429124"


def test_clinvar_returns_none_when_no_record_matches_the_alleles(snapshot):
    assert snapshot.clinvar("rs671", 111803962, "G", "C") is None


@pytest.mark.parametrize("status,stars", sorted(REVIEW_STATUS_STARS.items()))
def test_clinvar_review_status_table_is_exact(status, stars):
    assert REVIEW_STATUS_STARS[status] == stars


def test_clinvar_review_status_table_covers_the_spec():
    assert REVIEW_STATUS_STARS["practice guideline"] == 4
    assert REVIEW_STATUS_STARS["reviewed by expert panel"] == 3
    assert REVIEW_STATUS_STARS["criteria provided, multiple submitters, no conflicts"] == 2
    assert REVIEW_STATUS_STARS["criteria provided, single submitter"] == 1
    assert REVIEW_STATUS_STARS[CLINVAR_CONFLICTING] == 1
    assert REVIEW_STATUS_STARS["no assertion criteria provided"] == 0
    assert REVIEW_STATUS_STARS["no classification provided"] == 0


def _synthetic_summary(review_status="criteria provided, single submitter", **overrides):
    record = {
        "uid": "1",
        "obj_type": "single nucleotide variant",
        "accession": "VCV000000001",
        "accession_version": "VCV000000001.1",
        "title": "synthetic",
        "variation_set": [{
            "variation_xrefs": [{"db_source": "dbSNP", "db_id": "123"}],
            "canonical_spdi": "NC_000001.11:99:A:G",
        }],
        "germline_classification": {"description": "Pathogenic", "review_status": review_status},
    }
    record.update(overrides)
    return {"result": {"uids": ["1"], "1": record}}


def test_synthetic_clinvar_unknown_review_status_raises():
    """Synthetic edge case: a status outside ClinVar's vocabulary fails fast."""
    with pytest.raises(AdapterError, match="unknown ClinVar review status"):
        select_clinvar_record(_synthetic_summary("something new"), "rs123", 100, "A", "G")


def test_synthetic_clinvar_status_lookup_is_exact_not_substring():
    """Synthetic edge case: a truncated or padded status must not be matched by substring."""
    for status in ("criteria provided, multiple submitters", "Practice Guideline", "practice guideline "):
        with pytest.raises(AdapterError):
            select_clinvar_record(_synthetic_summary(status), "rs123", 100, "A", "G")


def test_synthetic_clinvar_missing_accession_is_none_with_a_reason_never_built_from_the_uid():
    """Synthetic edge case: CR-4, no accession in the payload means None, not VCV%09d from the uid."""
    summary = _synthetic_summary(accession="", accession_version="")
    record = select_clinvar_record(summary, "rs123", 100, "A", "G")
    assert record.accession is None and record.accession_version is None
    assert "accession" in record.reasons


def test_synthetic_clinvar_missing_classification_raises():
    """Synthetic edge case: a record without germline_classification cannot be read."""
    summary = _synthetic_summary()
    del summary["result"]["1"]["germline_classification"]
    with pytest.raises(AdapterError, match="germline_classification"):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def test_synthetic_clinvar_two_matching_single_variant_records_is_ambiguous():
    """Synthetic edge case: selection fails closed rather than picking one of two equal candidates."""
    summary = _synthetic_summary()
    second = copy.deepcopy(summary["result"]["1"])
    second["uid"], second["accession"] = "2", "VCV000000002"
    summary["result"]["uids"].append("2")
    summary["result"]["2"] = second
    with pytest.raises(AdapterError, match="several single-variant"):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def test_clinvar_truncated_esearch_is_refused():
    """L2: an esearch with count != len(idlist) is unverified (the first rs4244285 capture was truncated)."""
    search = read("clinvar", "rs429358.esearch")
    summary = read("clinvar", "rs429358")
    check_clinvar_search_complete(search, summary)
    truncated = copy.deepcopy(search)
    truncated["esearchresult"]["count"] = "37"
    with pytest.raises(AdapterError, match="truncated"):
        check_clinvar_search_complete(truncated, summary)


def test_clinvar_snapshot_refuses_a_summary_whose_search_was_truncated(tmp_path):
    """L2 end to end: a re-pinned (meta and sha consistent) truncated esearch still stops the import."""
    root = tmp_path / "real"
    shutil.copytree(REAL, root)
    body = root / "clinvar" / "rs429358.esearch.json"
    meta = root / "clinvar" / "rs429358.esearch.meta.json"
    data = body.read_bytes().replace(b'"count":"8"', b'"count":"37"')
    body.write_bytes(data)
    info = json.loads(meta.read_text(encoding="utf-8"))
    info["sha256_of_body"], info["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    meta.write_text(json.dumps(info), encoding="utf-8")
    assert verify_pinned_payloads(root) == []
    with pytest.raises(AdapterError, match="truncated"):
        UpstreamSnapshot(root).clinvar("rs429358", *locus_args("rs429358"))


def test_all_clinvar_searches_are_complete():
    for rsid in ALL_RSIDS:
        check_clinvar_search_complete(read("clinvar", f"{rsid}.esearch"), read("clinvar", rsid))


# ---------------------------------------------------------------------------
# dbSNP
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rsid", ALL_RSIDS)
def test_dbsnp_positions_and_alleles_for_every_locus(snapshot, rsid):
    record = snapshot.dbsnp(rsid)
    spdi37, spdi38 = SPDI_POSITIONS[rsid]
    assert record.rsid == rsid
    locus = LOCI[rsid]
    assert record.placements["GRCh37"].alleles[0][0] == spdi37
    assert record.placements["GRCh38"].alleles[0][0] == spdi38
    if len(locus["ref"]) == 1:
        # SPDI is 0-based: the KB position is spdi.position + 1.
        assert record.placements["GRCh37"].locate(locus["ref"], locus["alt"]) == spdi37 + 1
        assert record.placements["GRCh38"].locate(locus["ref"], locus["alt"]) == spdi38 + 1
    assert record.check_locus("GRCh37", locus["pos_grch37"], locus["ref"], locus["alt"]) is None
    assert record.check_locus("GRCh38", locus["pos_grch38"], locus["ref"], locus["alt"]) is None


def test_dbsnp_indel_is_compared_in_vcf_normalised_form(snapshot):
    """L8: dbSNP's TCTT>T at SPDI 117559590 equals the VCF anchored ATCT>A at 117559590 (1-based)."""
    record = snapshot.dbsnp("rs113993960")
    assert record.placements["GRCh38"].locate("ATCT", "A") == 117559590
    assert record.placements["GRCh37"].locate("ATCT", "A") == 117199644
    assert normalize_edit(117559590, "ATCT", "A") == normalize_edit(117559590 + 1, "TCTT", "T")
    assert record.check_locus("GRCh38", 117559591, "ATCT", "A") is not None, "an off-by-one anchor must not pass"
    assert record.placements["GRCh38"].locate("ATCT", "AG") is None, "an insertion dbSNP does not list"


def test_dbsnp_rs6025_grch37_reference_base_is_the_variant_allele(snapshot):
    """L1: the check is subset-of-allele-set, not ref == assembly reference."""
    record = snapshot.dbsnp("rs6025")
    assert record.placements["GRCh37"].alleles[0][1] == "T"
    assert record.check_locus("GRCh37", 169519049, "C", "T") is None


def test_dbsnp_rejects_wrong_position_and_alleles(snapshot):
    record = snapshot.dbsnp("rs671")
    assert "position" in record.check_locus("GRCh38", 111803963, "G", "A")
    assert "allele" in record.check_locus("GRCh38", 111803962, "G", "C")
    assert "placement" in parse_dbsnp({"refsnp_id": "1", "primary_snapshot_data": {"placements_with_allele": []}}).check_locus("GRCh38", 1, "A", "G")


def test_dbsnp_release_comes_from_the_payload(snapshot):
    record = snapshot.dbsnp("rs671")
    assert record.release == f"dbSNP build {read('dbsnp', 'rs671')['last_update_build_id']}"
    assert record.provenance.release == record.release


# ---------------------------------------------------------------------------
# Ensembl VEP
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rsid", ALL_RSIDS)
def test_vep_mane_select_transcript_for_every_locus(snapshot, rsid):
    locus = LOCI[rsid]
    record = snapshot.vep(rsid, locus["gene"], locus["ref"], locus["alt"])
    assert record.mane_select_refseq == MANE_REFSEQ[rsid]
    assert re.fullmatch(r"ENST\d{11}", record.mane_select_ensembl)


def test_vep_alphamissense_is_read_from_the_real_field_names(snapshot):
    """CR-7: the payload names them am_class and am_pathogenicity."""
    record = snapshot.vep("rs429358", "APOE", "T", "C")
    assert record.alphamissense_class == "likely_benign"
    assert record.alphamissense_score == 0.0365
    record = snapshot.vep("rs1800562", "HFE", "G", "A")
    assert (record.alphamissense_class, record.alphamissense_score) == ("likely_pathogenic", 0.9585)


def test_vep_alphamissense_is_none_when_the_payload_has_none(snapshot):
    """rs1799963 is a 3' UTR variant: the real payload carries no AlphaMissense block, so None with a reason."""
    record = snapshot.vep("rs1799963", "F2", "G", "A")
    assert record.alphamissense_class is None and record.alphamissense_score is None
    assert {"alphamissense_class", "alphamissense_score"} <= set(record.reasons)


def test_vep_picks_the_row_for_the_locus_allele_and_gene(snapshot):
    """rs1801133 lists a second allele (c.665C>G) and rs429358 a TOMM40 MANE row: neither may be chosen."""
    mthfr = snapshot.vep("rs1801133", "MTHFR", "G", "A")
    assert (mthfr.alphamissense_class, mthfr.alphamissense_score) == ("likely_pathogenic", 0.6324)
    assert snapshot.vep("rs429358", "APOE", "T", "C").mane_select_refseq == "NM_000041.4"


def test_vep_indel_allele_matches_in_normalised_form(snapshot):
    record = snapshot.vep("rs113993960", "CFTR", "ATCT", "A")
    assert record.mane_select_refseq == "NM_000492.4"


def _synthetic_vep(rows):
    return [{"id": "rs1", "allele_string": "A/G", "transcript_consequences": rows}]


def test_synthetic_vep_without_a_mane_row_is_none_there_is_no_fallback():
    """Synthetic edge case: CR-6, an Ensembl canonical transcript (canonical=1) is not MANE Select."""
    rows = [{"transcript_id": "ENST00000000001", "gene_symbol": "GENE", "canonical": 1,
             "variant_allele": "G", "mane_select": None}]
    record = parse_vep(_synthetic_vep(rows), "rs1", "GENE", "A", "G")
    assert record.mane_select_ensembl is None and record.mane_select_refseq is None
    assert "mane_select" in record.reasons


def test_synthetic_vep_mane_select_marker_is_the_only_source():
    """Synthetic edge case: a row with a mane_select accession but no MANE_Select marker is not trusted."""
    rows = [{"transcript_id": "ENST00000000001", "gene_symbol": "GENE", "mane_select": "NM_000001.1",
             "variant_allele": "G"}]
    assert parse_vep(_synthetic_vep(rows), "rs1", "GENE", "A", "G").mane_select_refseq is None


def test_synthetic_vep_old_alphamissense_field_names_are_not_read():
    """Synthetic edge case: CR-7, `pathogenicity` and `score` are not what the payload uses."""
    rows = [{"transcript_id": "ENST00000000001", "gene_symbol": "GENE", "mane": ["MANE_Select"],
             "mane_select": "NM_000001.1", "variant_allele": "G",
             "alphamissense": {"pathogenicity": "pathogenic", "score": 0.99}}]
    record = parse_vep(_synthetic_vep(rows), "rs1", "GENE", "A", "G")
    assert record.mane_select_refseq == "NM_000001.1"
    assert record.alphamissense_class is None and record.alphamissense_score is None


def test_synthetic_vep_payload_for_another_rsid_raises():
    """Synthetic edge case: a payload for a different variant is refused."""
    with pytest.raises(AdapterError):
        parse_vep(_synthetic_vep([]), "rs2", "GENE", "A", "G")


# ---------------------------------------------------------------------------
# gnomAD
# ---------------------------------------------------------------------------
def test_gnomad_af_pools_exome_and_genome_counts(snapshot):
    variant = snapshot.gnomad_variant("rs429358", "19-44908684-T-C")
    assert variant.variant_id == "19-44908684-T-C"
    assert variant.af == pytest.approx((208931 + 23933) / (1415800 + 152092))


def test_gnomad_af_uses_the_genome_record_alone_where_there_is_no_exome(snapshot):
    variant = snapshot.gnomad_variant("rs9923231", "16-31096368-C-T")
    assert variant.af == pytest.approx(48520 / 152092)


@pytest.mark.parametrize("rsid,variant_id", [("rs4244285", "10-94781859-G-A"), ("rs3918290", "1-97450058-C-T")])
def test_gnomad_multiallelic_rsids_use_the_per_variant_capture(snapshot, rsid, variant_id):
    """L6: the rsid query errors with 'Multiple variants found', so the per-variant file is read."""
    assert "Multiple variants" in json.dumps(read("gnomad", rsid))
    variant = snapshot.gnomad_variant(rsid, variant_id)
    assert variant.variant_id == variant_id and variant.af is not None and 0 < variant.af < 1


def test_gnomad_multiple_variants_error_gives_none_with_a_reason():
    raw = read("gnomad", "rs4244285")
    variant = parse_gnomad_variant(raw)
    assert variant.af is None and variant.variant_id is None
    assert "Multiple variants" in variant.reasons["af"]


def test_synthetic_gnomad_zero_an_is_none_not_a_division():
    """Synthetic edge case: an = 0 or missing counts never give 0.0."""
    raw = {"data": {"variant": {"variant_id": "1-1-A-G", "exome": {"ac": 0, "an": 0}, "genome": None}}}
    variant = parse_gnomad_variant(raw)
    assert variant.af is None and "af" in variant.reasons


@pytest.mark.parametrize("gene", sorted({locus["gene"] for locus in LOCI.values()}))
def test_gnomad_constraint_for_every_gene(snapshot, gene):
    constraint = snapshot.constraint(gene)
    assert constraint.symbol == gene
    assert constraint.pli is not None and 0 < constraint.pli <= 1
    assert constraint.loeuf is not None and constraint.loeuf > 0


def test_gnomad_constraint_loeuf_is_oe_lof_upper(snapshot):
    raw = read("gnomad", "constraint_APOE")
    assert snapshot.constraint("APOE").loeuf == raw["data"]["gene"]["gnomad_constraint"]["oe_lof_upper"]


def test_synthetic_gnomad_null_constraint_is_none_with_reasons():
    """Synthetic edge case: CR-5, a gene with gnomad_constraint null must not raise or give 0.0."""
    constraint = parse_gnomad_constraint({"data": {"gene": {"symbol": "X", "gnomad_constraint": None}}})
    assert constraint.pli is None and constraint.loeuf is None
    assert {"pli", "loeuf"} <= set(constraint.reasons)


def test_synthetic_gnomad_null_gene_is_none_with_reasons():
    """Synthetic edge case: no gene at all (unknown symbol)."""
    constraint = parse_gnomad_constraint({"data": {"gene": None}})
    assert constraint.pli is None and constraint.loeuf is None


def test_synthetic_gnomad_constraint_missing_loeuf_keeps_pli():
    """Synthetic edge case: partial constraint record."""
    constraint = parse_gnomad_constraint({"data": {"gene": {"symbol": "X", "gnomad_constraint": {"pli": 0.5}}}})
    assert constraint.pli == 0.5 and constraint.loeuf is None and "loeuf" in constraint.reasons


# ---------------------------------------------------------------------------
# Provenance and integrity
# ---------------------------------------------------------------------------
def test_provenance_comes_from_the_capture_meta(snapshot):
    meta = json.loads((REAL / "clinvar" / "rs671.meta.json").read_text(encoding="utf-8"))
    prov = snapshot.clinvar("rs671", *locus_args("rs671")).provenance
    assert (prov.url, prov.retrieved_at, prov.sha256) == (meta["url"], meta["retrieved_at"], meta["sha256_of_body"])
    as_dict = prov.to_dict()
    assert as_dict["curation_mode"] == "machine_imported"
    assert set(as_dict) == {"source", "release", "accession", "url", "curation_mode", "retrieved_at"}


def test_gnomad_release_comes_from_the_recorded_request(snapshot):
    assert snapshot.gnomad_variant("rs429358", "19-44908684-T-C").provenance.release == "gnomad_r4"
    assert snapshot.constraint("APOE").provenance.release is None


def test_pinned_payloads_match_their_sha256():
    assert verify_pinned_payloads(REAL) == []


def test_tampered_payload_is_detected(tmp_path):
    copy_root = tmp_path / "real"
    shutil.copytree(REAL, copy_root)
    target = copy_root / "dbsnp" / "rs671.json"
    target.write_bytes(target.read_bytes().replace(b"111803961", b"111803962", 1))
    errors = verify_pinned_payloads(copy_root)
    assert len(errors) == 1 and "dbsnp/rs671.json" in errors[0] and "sha256" in errors[0]
    with pytest.raises(PayloadIntegrityError):
        load_pinned(target)


def test_missing_directory_is_an_error(tmp_path):
    assert "not found" in verify_pinned_payloads(tmp_path / "absent")[0]


# ---------------------------------------------------------------------------
# Anti-corruption layer: structure
# ---------------------------------------------------------------------------
# Keys the adapters read that name no upstream payload field. Each group says why it is excluded.
_NOT_UPSTREAM_FIELDS = frozenset({
    # the capture meta format fetch_upstream.py writes and the adapters read back (our own file, not a payload)
    "bytes", "http_status", "request_body", "retrieved_at", "sha256_of_body", "url",
    # words that occur as ordinary identifiers, dict keys of our own models and CLI text everywhere
    "id", "data", "result", "errors", "message", "count", "gene", "symbol", "title", "description",
    "position", "variant", "uid", "uids", "allele", "alleles", "af", "pli", "loeuf",
    "significance", "accession", "alphamissense_class", "alphamissense_score",
    # our own build labels, keys of our DbsnpRecord.placements
    "GRCh37", "GRCh38",
    # a field of our own KB and models (contracts C2: evidence.clinvar.review_status)
    "review_status",
})


def _string_keys_read_by(path):
    """Every string constant used as a subscript, as the first argument of `.get(...)` or as the key of `_require(...)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            keys.add(node.slice.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_require"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            keys.add(node.args[1].value)  # _require(obj, "key", kind, where) reads "key"
    return keys


def _forbidden_upstream_names():
    return _string_keys_read_by(ROOT / "tools" / "source_adapters.py") - _NOT_UPSTREAM_FIELDS


# The desktop VEP parser is a known second reader of the payload (review S3a-C-2); S4 owns its removal.
_KNOWN_LEAKS = {"biotools_orchestrator.py": "review S3a-C-2, owned by S4"}


def _tracked_python_files():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for name in out.splitlines():
        path = ROOT / name
        parts = Path(name).parts
        if path.name == "source_adapters.py" or parts[0] == "tests" or "fixtures" in parts:
            continue
        yield path


def _leaks(path, forbidden):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)} & forbidden)


def test_forbidden_names_are_derived_from_the_adapters():
    names = _forbidden_upstream_names()
    for name in ("variation_set", "esearchresult", "idlist", "primary_snapshot_data", "placement_annot",
                 "seq_id_traits_by_assembly", "variant_allele", "mane_select", "am_class", "germline_classification"):
        assert name in names
    assert len(names) >= 25


def test_only_source_adapters_names_upstream_fields():
    """AGENTS.md section 2: no tracked module outside the adapters and the tests may know a payload field."""
    forbidden = _forbidden_upstream_names()
    scanned = [path.name for path in _tracked_python_files()]
    assert "fetch_upstream.py" in scanned and "build_canonical_kb.py" in scanned and "genomic_parser.py" in scanned
    for path in _tracked_python_files():
        found = _leaks(path, forbidden)
        if path.name in _KNOWN_LEAKS:
            continue
        assert not found, f"{path.relative_to(ROOT)} names upstream fields {found}"


def test_the_guard_flags_a_leak(tmp_path):
    leaky = tmp_path / "leaky.py"
    leaky.write_text('def f(raw):\n    return raw["variation_set"]\n', encoding="utf-8")
    assert _leaks(leaky, _forbidden_upstream_names()) == ["variation_set"]


def test_known_leaks_are_listed_and_still_leak():
    """The allow-list must not outlive the leak: when S4 removes the second VEP parser this fails."""
    forbidden = _forbidden_upstream_names()
    for name in _KNOWN_LEAKS:
        assert _leaks(ROOT / name, forbidden), f"{name} no longer leaks: drop it from _KNOWN_LEAKS"


def test_adapters_exist_only_for_sources_with_real_payloads():
    for gone in ("CpicSourceAdapter", "AlphaFoldSourceAdapter", "HpaSourceAdapter", "EncodeSourceAdapter"):
        assert not hasattr(source_adapters, gone)
    assert not hasattr(source_adapters, "derive_evidence_tier"), "one tier function lives in coverage_taxonomy (CR-3)"
    for source in ("alphafold", "cpic", "encode", "hpa"):
        assert not (REAL.parent / source).exists()


# ---------------------------------------------------------------------------
# Capture-script helpers (S3-F2a): payload knowledge lives here, not in fetch_upstream.py
# ---------------------------------------------------------------------------
def _real_body(source, key):
    return (REAL / source / f"{key}.json").read_bytes()


def test_esearch_uids_reads_a_real_capture_and_accepts_zero_hits():
    body = _real_body("clinvar", "rs4244285.esearch")
    assert esearch_uids(body) == [str(u) for u in json.loads(body)["esearchresult"]["idlist"]]
    assert len(esearch_uids(body)) > 1
    assert esearch_uids(b'{"esearchresult": {"count": "0", "idlist": []}}') == []


def test_esearch_uids_is_the_one_completeness_rule():
    truncated = b'{"esearchresult": {"count": "37", "idlist": ["1", "2"]}}'
    with pytest.raises(TruncatedSearch, match="truncated"):
        esearch_uids(truncated)
    assert issubclass(TruncatedSearch, AdapterError)
    with pytest.raises(AdapterError, match="truncated"):
        check_clinvar_search_complete(json.loads(truncated), {"result": {"uids": ["1", "2"]}})


@pytest.mark.parametrize("body", [
    b"{}", b"not json", b'{"esearchresult": {}}',
    b'{"esearchresult": {"count": "x", "idlist": []}}', b'{"esearchresult": {"count": "1", "idlist": 5}}',
])
def test_esearch_uids_raises_on_a_malformed_body_instead_of_returning_nothing(body):
    with pytest.raises(AdapterError):
        esearch_uids(body)


_GNOMAD_IDS = {
    "rs429358": ["19-44908684-T-C"], "rs7412": ["19-44908822-C-T"],
    "rs1800562": ["6-26092913-G-A", "6-26092913-G-T"], "rs1799945": ["6-26090951-C-G", "6-26090951-C-T"],
    "rs6025": ["1-169549811-C-A", "1-169549811-C-G", "1-169549811-C-T"], "rs1799963": ["11-46739505-G-A"],
    "rs4244285": ["10-94781859-G-A", "10-94781859-G-C", "10-94781859-G-T"],
    "rs9923231": ["16-31096368-C-A", "16-31096368-C-G", "16-31096368-C-T"],
    "rs4149056": ["12-21178615-T-A", "12-21178615-T-C"],
    "rs3918290": ["1-97450058-C-A", "1-97450058-C-G", "1-97450058-C-T"],
    "rs1801133": ["1-11796321-G-A", "1-11796321-G-C", "1-11796321-G-T"],
    "rs4988235": ["2-135851076-G-A", "2-135851076-G-C", "2-135851076-G-T"],
    "rs671": ["12-111803962-G-A"], "rs113993960": ["7-117559591-TCTT-T", "7-117559591-TCTT-TCTTCTT"],
}


@pytest.mark.parametrize("rsid", sorted(_GNOMAD_IDS))
def test_gnomad_variant_ids_from_each_real_dbsnp_capture(rsid):
    assert gnomad_variant_ids_from_dbsnp(json.loads(_real_body("dbsnp", rsid))) == _GNOMAD_IDS[rsid]


def test_synthetic_dbsnp_without_a_grch38_placement_raises():
    """Synthetic: a refsnp with no chromosome placement must not give an empty id list."""
    with pytest.raises(AdapterError, match="GRCh38"):
        gnomad_variant_ids_from_dbsnp({"refsnp_id": "1", "primary_snapshot_data": {"placements_with_allele": []}})


def test_gnomad_multiple_variants_refusal_is_recognised_through_the_parser():
    assert is_multiple_variants_refusal(_real_body("gnomad", "rs4244285")) is True
    assert is_multiple_variants_refusal(_real_body("gnomad", "rs671")) is False
    assert is_multiple_variants_refusal({"errors": [{"message": "Multiple variants found, x"}]}) is True
    with pytest.raises(AdapterError):
        is_multiple_variants_refusal(b"<html>502</html>")


# ---------------------------------------------------------------------------
# S3-F2b: the adapters refuse what they cannot read (S3a-C-4, C-5, C-7, C-13, C-15)
# Every test below is synthetic (hand-built bytes) and names the branch it guards.
# ---------------------------------------------------------------------------
def _repin(root, source, key, data):
    """Replace a capture body and re-pin it (meta sha and size agree), so only the adapter can object."""
    body = root / source / f"{key}.json"
    meta = root / source / f"{key}.meta.json"
    body.write_bytes(data)
    info = json.loads(meta.read_text(encoding="utf-8"))
    info["sha256_of_body"], info["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    meta.write_text(json.dumps(info), encoding="utf-8")


def _edit_meta(root, source, key, **change):
    meta = root / source / f"{key}.meta.json"
    info = json.loads(meta.read_text(encoding="utf-8"))
    info.update(change)
    meta.write_text(json.dumps(info), encoding="utf-8")
    return info


@pytest.fixture
def pinned_copy(tmp_path):
    root = tmp_path / "real"
    shutil.copytree(REAL, root)
    return root


# --- C-4: ClinVar -----------------------------------------------------------
@pytest.mark.parametrize("field", ["title", "obj_type"])
def test_synthetic_clinvar_matching_record_without_title_or_obj_type_raises(field):
    """C-4: a matching record that loses title or obj_type is refused, not read as title ''."""
    summary = _synthetic_summary()
    del summary["result"]["1"][field]
    with pytest.raises(AdapterError, match=field):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def test_synthetic_clinvar_mistyped_title_raises():
    with pytest.raises(AdapterError, match="title"):
        select_clinvar_record(_synthetic_summary(title=5), "rs123", 100, "A", "G")


def test_synthetic_clinvar_uid_listed_without_an_entry_raises_adapter_error():
    """C-4: `records[uid]` must not escape as a KeyError (the build's handler catches AdapterError)."""
    summary = _synthetic_summary()
    summary["result"]["uids"].append("2")
    with pytest.raises(AdapterError, match="result.2 is missing"):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def test_synthetic_clinvar_summary_without_result_raises():
    with pytest.raises(AdapterError, match="result"):
        select_clinvar_record({}, "rs123", 100, "A", "G")


@pytest.mark.parametrize("spdi", [None, 5, "NC_000001.11:99:A", "NC_000001.11:x:A:G"])
def test_synthetic_clinvar_unreadable_spdi_on_an_xref_match_raises(spdi):
    """C-4: an xref-matching record whose canonical_spdi is absent or malformed is refused, not dropped."""
    summary = _synthetic_summary()
    variation = summary["result"]["1"]["variation_set"][0]
    if spdi is None:
        del variation["canonical_spdi"]
    else:
        variation["canonical_spdi"] = spdi
    with pytest.raises(AdapterError, match="canonical_spdi"):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def test_synthetic_clinvar_record_for_another_rsid_with_no_spdi_is_still_skipped():
    """C-4 scope: only an xref-matching record must carry a readable SPDI."""
    summary = _synthetic_summary()
    del summary["result"]["1"]["variation_set"][0]["canonical_spdi"]
    assert select_clinvar_record(summary, "rs999", 100, "A", "G") is None


def test_synthetic_clinvar_spdi_on_another_sequence_raises():
    """C-4: the SPDI sequence id is compared with the GRCh38 chromosome of the locus, not dropped."""
    summary = _synthetic_summary()
    with pytest.raises(AdapterError, match="NC_000002.12"):
        select_clinvar_record(summary, "rs123", 100, "A", "G", seq_id="NC_000002.12")
    assert select_clinvar_record(summary, "rs123", 100, "A", "G", seq_id="NC_000001.11") is not None


def test_clinvar_snapshot_compares_the_spdi_sequence_with_the_dbsnp_grch38_chromosome(pinned_copy):
    """C-4 end to end: the dbSNP capture names the GRCh38 chromosome; a ClinVar SPDI elsewhere is refused."""
    raw = (pinned_copy / "clinvar" / "rs671.json").read_bytes()
    assert b"NC_000012.12:" in raw
    _repin(pinned_copy, "clinvar", "rs671", raw.replace(b"NC_000012.12:", b"NC_000012.11:"))
    with pytest.raises(AdapterError, match="NC_000012.11"):
        UpstreamSnapshot(pinned_copy).clinvar("rs671", *locus_args("rs671"))


def test_synthetic_clinvar_search_check_needs_the_esummary_uids():
    with pytest.raises(AdapterError, match="uids"):
        check_clinvar_search_complete({"esearchresult": {"count": "0", "idlist": []}}, {"result": {}})


# --- C-4: dbSNP -------------------------------------------------------------
def _synthetic_dbsnp():
    return copy.deepcopy(read("dbsnp", "rs671"))


def _grch38_placement(raw):
    return next(p for p in raw["primary_snapshot_data"]["placements_with_allele"] if p["seq_id"] == "NC_000012.12")


@pytest.mark.parametrize("path", ["primary_snapshot_data", "refsnp_id"])
def test_synthetic_dbsnp_missing_top_level_field_raises(path):
    raw = _synthetic_dbsnp()
    del raw[path]
    with pytest.raises(AdapterError, match=path):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_without_placements_raises_not_an_empty_record():
    raw = _synthetic_dbsnp()
    del raw["primary_snapshot_data"]["placements_with_allele"]
    with pytest.raises(AdapterError, match="placements_with_allele"):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_refsnp_id_is_never_rendered_as_rsnone():
    raw = _synthetic_dbsnp()
    raw["refsnp_id"] = None
    with pytest.raises(AdapterError, match="refsnp_id"):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_placement_without_seq_id_raises():
    raw = _synthetic_dbsnp()
    del _grch38_placement(raw)["seq_id"]
    with pytest.raises(AdapterError, match="seq_id"):
        parse_dbsnp(raw)


@pytest.mark.parametrize("field", ["position", "deleted_sequence", "inserted_sequence"])
def test_synthetic_dbsnp_allele_without_position_or_sequence_raises(field):
    raw = _synthetic_dbsnp()
    del _grch38_placement(raw)["alleles"][0]["allele"]["spdi"][field]
    with pytest.raises(AdapterError, match=field):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_string_position_raises():
    raw = _synthetic_dbsnp()
    _grch38_placement(raw)["alleles"][0]["allele"]["spdi"]["position"] = "111803961"
    with pytest.raises(AdapterError, match="position"):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_allele_without_spdi_raises():
    raw = _synthetic_dbsnp()
    del _grch38_placement(raw)["alleles"][0]["allele"]["spdi"]
    with pytest.raises(AdapterError, match="spdi"):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_two_grch38_chromosome_placements_raise():
    """C-13: the 'several chromosome placements' guard."""
    raw = _synthetic_dbsnp()
    raw["primary_snapshot_data"]["placements_with_allele"].append(copy.deepcopy(_grch38_placement(raw)))
    with pytest.raises(AdapterError, match="several GRCh38 chromosome placements"):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_payload_for_another_rsid_raises(pinned_copy):
    """C-13: the 'dbSNP payload is for' guard."""
    _repin(pinned_copy, "dbsnp", "rs671", (REAL / "dbsnp" / "rs7412.json").read_bytes())
    with pytest.raises(AdapterError, match="dbSNP payload is for rs7412"):
        UpstreamSnapshot(pinned_copy).dbsnp("rs671")


# --- C-4: VEP ---------------------------------------------------------------
def _vep_row(**alphamissense):
    row = {"transcript_id": "ENST00000000001", "gene_symbol": "GENE", "mane": ["MANE_Select"],
           "mane_select": "NM_000001.1", "variant_allele": "G"}
    if alphamissense:
        row["alphamissense"] = alphamissense
    return row


@pytest.mark.parametrize("score", ["0.5", True, [0.5]])
def test_synthetic_vep_mistyped_alphamissense_score_raises_adapter_error(score):
    """C-4: float('x') would raise a bare ValueError; a string score is a schema change, not a number."""
    with pytest.raises(AdapterError, match="am_pathogenicity"):
        parse_vep(_synthetic_vep([_vep_row(am_class="ambiguous", am_pathogenicity=score)]), "rs1", "GENE", "A", "G")


@pytest.mark.parametrize("am_class", ["benign", "", 3, "Ambiguous"])
def test_synthetic_vep_unknown_alphamissense_class_raises(am_class):
    """C-4: the class vocabulary is closed (likely_benign, ambiguous, likely_pathogenic)."""
    with pytest.raises(AdapterError, match="am_class"):
        parse_vep(_synthetic_vep([_vep_row(am_class=am_class, am_pathogenicity=0.5)]), "rs1", "GENE", "A", "G")


def test_synthetic_vep_alphamissense_vocabulary_is_accepted():
    for am_class in ("likely_benign", "ambiguous", "likely_pathogenic"):
        record = parse_vep(_synthetic_vep([_vep_row(am_class=am_class, am_pathogenicity=1)]), "rs1", "GENE", "A", "G")
        assert record.alphamissense_class == am_class and record.alphamissense_score == 1.0


def test_synthetic_vep_alphamissense_that_is_not_an_object_raises():
    row = _vep_row()
    row["alphamissense"] = "likely_benign"
    with pytest.raises(AdapterError, match="alphamissense"):
        parse_vep(_synthetic_vep([row]), "rs1", "GENE", "A", "G")


def test_synthetic_vep_two_mane_select_transcripts_raise():
    """C-13: the 'several MANE Select transcripts' guard."""
    second = _vep_row()
    second["transcript_id"], second["mane_select"] = "ENST00000000002", "NM_000002.1"
    with pytest.raises(AdapterError, match="several MANE Select transcripts"):
        parse_vep(_synthetic_vep([_vep_row(), second]), "rs1", "GENE", "A", "G")


# --- C-4: the meta and load_pinned -------------------------------------------
def test_synthetic_meta_without_url_raises_adapter_error_naming_the_field(pinned_copy):
    meta = pinned_copy / "clinvar" / "rs671.meta.json"
    info = json.loads(meta.read_text(encoding="utf-8"))
    del info["url"]
    meta.write_text(json.dumps(info), encoding="utf-8")
    with pytest.raises(AdapterError, match="url"):
        UpstreamSnapshot(pinned_copy).clinvar("rs671", *locus_args("rs671"))


def test_synthetic_meta_with_a_mistyped_url_raises(pinned_copy):
    _edit_meta(pinned_copy, "dbsnp", "rs671", url=None)
    with pytest.raises(AdapterError, match="url"):
        UpstreamSnapshot(pinned_copy).dbsnp("rs671")


@pytest.mark.parametrize("which,data", [
    ("meta", b"{not json"), ("meta", b"\xff\xfe"), ("meta", b"[]"),
    ("body", b"{not json"), ("body", b"\xff\xfe"),
])
def test_load_pinned_wraps_json_and_decode_errors_in_payload_integrity_error(pinned_copy, which, data):
    """C-4: a corrupt meta or body is a PayloadIntegrityError, never a bare JSONDecodeError/UnicodeDecodeError."""
    if which == "meta":
        (pinned_copy / "dbsnp" / "rs671.meta.json").write_bytes(data)
    else:
        _repin(pinned_copy, "dbsnp", "rs671", data)
    with pytest.raises(PayloadIntegrityError):
        load_pinned(pinned_copy / "dbsnp" / "rs671.json")


def test_load_pinned_refuses_a_missing_body_or_meta(pinned_copy):
    """C-13: the OSError branch."""
    (pinned_copy / "dbsnp" / "rs671.json").unlink()
    with pytest.raises(PayloadIntegrityError, match="cannot read"):
        load_pinned(pinned_copy / "dbsnp" / "rs671.json")
    (pinned_copy / "dbsnp" / "rs7412.meta.json").unlink()
    with pytest.raises(PayloadIntegrityError, match="cannot read"):
        load_pinned(pinned_copy / "dbsnp" / "rs7412.json")


@pytest.mark.parametrize("change", [{"http_status": 500}, {"http_status": 204}, {"sha256_of_body": None}])
def test_load_pinned_refuses_a_capture_that_was_not_a_successful_response(pinned_copy, change):
    """C-13: the 'capture was not a successful response' guard (only a 200 with a sha is a capture)."""
    _edit_meta(pinned_copy, "dbsnp", "rs671", **change)
    with pytest.raises(PayloadIntegrityError, match="not a successful response"):
        load_pinned(pinned_copy / "dbsnp" / "rs671.json")


# --- C-7 / C-13: verify_pinned_payloads ---------------------------------------
def test_verify_reports_a_directory_with_no_pinned_payloads(tmp_path):
    """C-13: the 'no pinned payloads' guard."""
    (tmp_path / "empty").mkdir()
    errors = verify_pinned_payloads(tmp_path / "empty")
    assert len(errors) == 1 and "no pinned payloads" in errors[0]


def test_verify_reports_an_unreadable_meta_or_missing_body(pinned_copy):
    """C-13: the 'unreadable' guard, for a missing body and for a meta that is not JSON."""
    (pinned_copy / "dbsnp" / "rs671.json").unlink()
    (pinned_copy / "dbsnp" / "rs7412.meta.json").write_text("{nope", encoding="utf-8")
    errors = verify_pinned_payloads(pinned_copy)
    assert len(errors) == 2 and all("unreadable" in e for e in errors)


def test_verify_reports_a_size_that_differs_from_the_meta(pinned_copy):
    """C-13: the size-mismatch branch (sha agrees, bytes does not)."""
    info = json.loads((pinned_copy / "dbsnp" / "rs671.meta.json").read_text(encoding="utf-8"))
    _edit_meta(pinned_copy, "dbsnp", "rs671", bytes=info["bytes"] + 1)
    errors = verify_pinned_payloads(pinned_copy)
    assert len(errors) == 1 and "dbsnp/rs671.json" in errors[0] and "size" in errors[0]


def test_verify_reports_a_body_that_sits_next_to_a_failure_meta(pinned_copy):
    """C-7: a failed re-capture that left the old body behind is an error, not a silent skip."""
    _edit_meta(pinned_copy, "dbsnp", "rs671", http_status=500, sha256_of_body=None)
    errors = verify_pinned_payloads(pinned_copy)
    assert len(errors) == 1 and "dbsnp/rs671.json" in errors[0] and "failure" in errors[0]


def test_verify_accepts_a_failure_meta_with_no_body(pinned_copy):
    """C-7: a recorded failure with no body is the honest state."""
    _edit_meta(pinned_copy, "dbsnp", "rs671", http_status=500, sha256_of_body=None)
    (pinned_copy / "dbsnp" / "rs671.json").unlink()
    assert verify_pinned_payloads(pinned_copy) == []


# --- C-13: ClinVar selection and completeness guards --------------------------
def test_synthetic_clinvar_two_star_allele_haplotype_records_raise():
    """C-13: the 'several star-allele haplotype records' guard."""
    summary = _synthetic_summary(obj_type="Haplotype", title="GENE*2")
    second = copy.deepcopy(summary["result"]["1"])
    second["uid"], second["accession"] = "2", "VCV000000002"
    summary["result"]["uids"].append("2")
    summary["result"]["2"] = second
    with pytest.raises(AdapterError, match="several star-allele"):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def test_clinvar_snapshot_without_an_esearch_capture_raises(pinned_copy):
    """C-13 / L2: an esummary with no esearch capture cannot prove it is complete."""
    (pinned_copy / "clinvar" / "rs671.esearch.json").unlink()
    (pinned_copy / "clinvar" / "rs671.esearch.meta.json").unlink()
    with pytest.raises(AdapterError, match="no esearch capture"):
        UpstreamSnapshot(pinned_copy).clinvar("rs671", *locus_args("rs671"))


def test_clinvar_esummary_covering_other_ids_than_the_esearch_raises():
    """C-13 / L2: the set(ids) != set(uids) branch of check_clinvar_search_complete."""
    search = read("clinvar", "rs429358.esearch")
    summary = copy.deepcopy(read("clinvar", "rs429358"))
    summary["result"]["uids"] = summary["result"]["uids"][:-1]
    with pytest.raises(AdapterError, match="does not cover exactly"):
        check_clinvar_search_complete(search, summary)


# --- C-5: gnomAD --------------------------------------------------------------
def _gnomad(exome=None, genome=None, **extra):
    return {"data": {"variant": {"variant_id": "1-1-A-G", "exome": exome, "genome": genome}}, **extra}


@pytest.mark.parametrize("ac", [None, "5", 5.0, True, -1, 11])
def test_synthetic_gnomad_ac_outside_zero_to_an_raises(ac):
    """C-5: an > 0 with ac null, mistyped, negative or above an is refused, never skipped or pooled."""
    with pytest.raises(AdapterError, match="ac"):
        parse_gnomad_variant(_gnomad(exome={"ac": ac, "an": 10}, genome={"ac": 1, "an": 10}))


@pytest.mark.parametrize("an", ["10", 1.5, True, -3])
def test_synthetic_gnomad_mistyped_an_raises(an):
    with pytest.raises(AdapterError, match="an"):
        parse_gnomad_variant(_gnomad(exome={"ac": 1, "an": an}))


def test_synthetic_gnomad_ac_equal_to_an_and_zero_are_valid():
    assert parse_gnomad_variant(_gnomad(exome={"ac": 10, "an": 10}, genome={"ac": 0, "an": 10})).af == pytest.approx(0.5)


def test_synthetic_gnomad_record_that_is_not_an_object_raises():
    with pytest.raises(AdapterError, match="exome"):
        parse_gnomad_variant(_gnomad(exome=[1, 2]))


def test_synthetic_gnomad_errors_beside_a_variant_raise():
    """C-5: a partial GraphQL response (variant plus errors) is not accepted."""
    raw = _gnomad(exome={"ac": 1, "an": 10}, errors=[{"message": "timeout in genome"}])
    with pytest.raises(AdapterError, match="timeout in genome"):
        parse_gnomad_variant(raw)


def test_synthetic_gnomad_empty_errors_list_beside_a_variant_is_accepted():
    assert parse_gnomad_variant(_gnomad(exome={"ac": 1, "an": 10}, errors=[])).af == pytest.approx(0.1)


def test_synthetic_gnomad_meta_without_the_dataset_raises(pinned_copy):
    """C-5: provenance must record the dataset; a meta whose request lacks it is refused, not given release None."""
    info = json.loads((pinned_copy / "gnomad" / "rs429358.meta.json").read_text(encoding="utf-8"))
    _edit_meta(pinned_copy, "gnomad", "rs429358", request_body=info["request_body"].replace("dataset: gnomad_r4", ""))
    with pytest.raises(AdapterError, match="dataset"):
        UpstreamSnapshot(pinned_copy).gnomad_variant("rs429358", "19-44908684-T-C")


def test_synthetic_gnomad_meta_without_a_request_body_raises(pinned_copy):
    _edit_meta(pinned_copy, "gnomad", "rs429358", request_body=None)
    with pytest.raises(AdapterError, match="dataset"):
        UpstreamSnapshot(pinned_copy).gnomad_variant("rs429358", "19-44908684-T-C")


# --- C-15 (test half): a curated locus with a missing capture is visible ----------
@pytest.mark.parametrize("rsid", ALL_RSIDS)
def test_every_curated_locus_has_all_its_pinned_captures(rsid):
    """C-15: 'never captured' and 'deleted' must not look alike; the committed tree holds every capture."""
    captures = (("clinvar", rsid), ("clinvar", f"{rsid}.esearch"), ("dbsnp", rsid), ("ensembl", rsid), ("gnomad", rsid),
                ("gnomad", f"constraint_{LOCI[rsid]['gene']}"))
    for source, key in captures:
        assert (REAL / source / f"{key}.json").is_file(), f"{source}/{key}.json"
        assert (REAL / source / f"{key}.meta.json").is_file(), f"{source}/{key}.meta.json"


# ---------------------------------------------------------------------------
# S3-F2b fix round: every fail-fast branch has a test that fails when the branch is reverted
# ---------------------------------------------------------------------------
def _without(container, *path):
    """Delete the key at the end of `path` (keys and list indexes) from `container` and return the container."""
    node = container
    for step in path[:-1]:
        node = node[step]
    del node[path[-1]]
    return container


@pytest.mark.parametrize("path,message", [
    (("result", "1", "variation_set"), "ClinVar record '1'.variation_set is missing"),
    (("result", "1", "variation_set", 0, "variation_xrefs"), r"variation_set\[\].variation_xrefs is missing"),
    (("result", "uids"), "ClinVar esummary.result.uids is missing"),
])
def test_synthetic_clinvar_selection_refuses_a_missing_structure_key(path, message):
    """Branches variation_set, variation_xrefs and esummary.result.uids of select_clinvar_record."""
    with pytest.raises(AdapterError, match=message):
        select_clinvar_record(_without(_synthetic_summary(), *path), "rs123", 100, "A", "G")


@pytest.mark.parametrize("key,message", [
    ("variation_set", "variation_set must be list, got dict"),
    ("variation_xrefs", "variation_xrefs must be list, got dict"),
    ("uids", "uids must be list, got dict"),
])
def test_synthetic_clinvar_selection_refuses_a_mistyped_structure_key(key, message):
    summary = _synthetic_summary()
    record = summary["result"]["1"]
    if key == "variation_set":
        record["variation_set"] = {}
    elif key == "variation_xrefs":
        record["variation_set"][0]["variation_xrefs"] = {}
    else:
        summary["result"]["uids"] = {}
    with pytest.raises(AdapterError, match=message):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


def _placement_path(raw, *tail):
    index = raw["primary_snapshot_data"]["placements_with_allele"].index(_grch38_placement(raw))
    return ("primary_snapshot_data", "placements_with_allele", index, *tail)


@pytest.mark.parametrize("tail,message", [
    (("placement_annot",), r"placements_with_allele\[\].placement_annot is missing"),
    (("placement_annot", "seq_type"), "placement_annot.seq_type is missing"),
    (("placement_annot", "seq_id_traits_by_assembly"), "placement_annot.seq_id_traits_by_assembly is missing"),
    (("placement_annot", "seq_id_traits_by_assembly", 0, "assembly_name"),
     r"seq_id_traits_by_assembly\[\].assembly_name is missing"),
    (("alleles",), r"placements_with_allele\[\].alleles is missing"),
])
def test_synthetic_dbsnp_refuses_a_missing_placement_structure_key(tail, message):
    """Branches placement_annot, seq_type, seq_id_traits_by_assembly, assembly_name and the alleles container."""
    raw = _synthetic_dbsnp()
    _without(raw, *_placement_path(raw, *tail))
    with pytest.raises(AdapterError, match=message):
        parse_dbsnp(raw)


def test_synthetic_dbsnp_refuses_a_mistyped_assembly_name():
    raw = _synthetic_dbsnp()
    annot = _grch38_placement(raw)["placement_annot"]
    annot["seq_id_traits_by_assembly"][0]["assembly_name"] = None
    with pytest.raises(AdapterError, match="assembly_name must be str, got NoneType"):
        parse_dbsnp(raw)


def test_synthetic_meta_without_retrieved_at_raises_adapter_error_naming_the_field(pinned_copy):
    """Branch retrieved_at of PinnedPayload.provenance."""
    meta = pinned_copy / "dbsnp" / "rs671.meta.json"
    info = json.loads(meta.read_text(encoding="utf-8"))
    del info["retrieved_at"]
    meta.write_text(json.dumps(info), encoding="utf-8")
    with pytest.raises(AdapterError, match="retrieved_at is missing"):
        UpstreamSnapshot(pinned_copy).dbsnp("rs671")


# --- VEP row reads ------------------------------------------------------------
@pytest.mark.parametrize("key", ["allele_string", "transcript_consequences"])
def test_synthetic_vep_record_without_a_row_field_raises(key):
    raw = _synthetic_vep([_vep_row()])
    del raw[0][key]
    with pytest.raises(AdapterError, match=f"{key} is missing"):
        parse_vep(raw, "rs1", "GENE", "A", "G")


@pytest.mark.parametrize("key,value", [("allele_string", None), ("transcript_consequences", {})])
def test_synthetic_vep_record_with_a_mistyped_row_field_raises(key, value):
    raw = _synthetic_vep([_vep_row()])
    raw[0][key] = value
    with pytest.raises(AdapterError, match=key):
        parse_vep(raw, "rs1", "GENE", "A", "G")


@pytest.mark.parametrize("row", [None, "ENST00000000001", [1]])
def test_synthetic_vep_consequence_that_is_not_an_object_raises_adapter_error(row):
    with pytest.raises(AdapterError, match="transcript_consequences"):
        parse_vep(_synthetic_vep([_vep_row(), row]), "rs1", "GENE", "A", "G")


def test_synthetic_vep_mane_row_for_the_gene_without_a_variant_allele_raises():
    row = _vep_row()
    del row["variant_allele"]
    with pytest.raises(AdapterError, match="variant_allele is missing"):
        parse_vep(_synthetic_vep([row]), "rs1", "GENE", "A", "G")


def test_synthetic_vep_row_for_another_gene_needs_no_variant_allele():
    """A row the filter drops before the allele comparison may lack variant_allele."""
    other = {"transcript_id": "ENST00000000009", "gene_symbol": "OTHER"}
    assert parse_vep(_synthetic_vep([other, _vep_row()]), "rs1", "GENE", "A", "G").mane_select_refseq == "NM_000001.1"


# --- the star-allele error message --------------------------------------------
def test_synthetic_clinvar_star_allele_error_is_readable_when_a_record_has_no_accession():
    summary = _synthetic_summary(obj_type="Haplotype", title="GENE*2")
    second = copy.deepcopy(summary["result"]["1"])
    second["uid"] = "2"
    for record in (summary["result"]["1"], second):
        del record["accession"]
    summary["result"]["uids"].append("2")
    summary["result"]["2"] = second
    with pytest.raises(AdapterError, match="several star-allele"):
        select_clinvar_record(summary, "rs123", 100, "A", "G")


# --- gnomAD: a record with ac but no an ---------------------------------------
def test_synthetic_gnomad_record_with_ac_but_no_an_key_raises():
    with pytest.raises(AdapterError, match="exome.an is missing"):
        parse_gnomad_variant(_gnomad(exome={"ac": 1}))


def test_synthetic_gnomad_record_with_an_null_is_still_skipped():
    """Real exome records carry an: null; only a missing key is a partial record."""
    assert parse_gnomad_variant(_gnomad(exome={"ac": None, "an": None}, genome={"ac": 1, "an": 10})).af == pytest.approx(0.1)
