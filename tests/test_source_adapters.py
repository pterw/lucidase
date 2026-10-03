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
    assert "placement" in parse_dbsnp({"refsnp_id": "1", "primary_snapshot_data": {}}).check_locus("GRCh38", 1, "A", "G")


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
    """Every string constant used as a subscript or as the first argument of `.get(...)` in a module."""
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
