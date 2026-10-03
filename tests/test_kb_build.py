"""
Tests for the knowledge-base build (contract C2, schema v2).

The build runs in memory from tools/curation/kb_curation.json. These tests never read the
committed web/src/knowledge-base.json (that is the job of `build_canonical_kb.py --verify-only`).
"""

import copy
from dataclasses import replace
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.build_canonical_kb import (
    DEFAULT_CURATION_PATH,
    _check_imported_ranges,
    build_kb,
    load_curation,
    render_kb,
    validate_curation,
)
from tools.source_adapters import UpstreamSnapshot
from tools.coverage_taxonomy import (
    ACMG_SINGLE_LOCUS_CAVEAT,
    INCOMPLETE_STAR_ALLELE_REFUSAL,
    EvidenceSufficiency,
    EvidenceTier,
    derive_evidence_sufficiency,
    derive_evidence_tier,
    derive_tier_from_cpic_level,
)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "build_canonical_kb.py"

# ---------------------------------------------------------------------------
# Expected data, written out independently of the curation file.
# Source: reports/t2-allele-table.md, from the pinned dbSNP payloads in
# tools/fixtures/upstream/real/dbsnp (SPDI positions are 0-based; KB positions are SPDI + 1).
# `alt` is the clinically relevant variant allele on the plus strand (constraints L1).
# Each entry: (spdi_grch37, alleles_grch37, spdi_grch38, alleles_grch38, ref, alt)
# where alleles_* is the whole dbSNP allele set (reference plus every listed alt) for that build.
# ---------------------------------------------------------------------------
EXPECTED = {
    # Indel in VCF-normalised left-aligned anchor form (constraints L8): dbSNP's TCTT>T at SPDI
    # 117559590 (GRCh38) / 117199644 (GRCh37) becomes ATCT>A anchored one base to the left, as gnomAD writes
    # 7-117559590-ATCT-A. The SPDI values below are the 0-based anchor positions (VCF pos - 1).
    "rs113993960": (117199643, {"ATCT", "A"}, 117559589, {"ATCT", "A"}, "ATCT", "A"),
    "rs1799945": (26091178, {"C", "G", "T"}, 26090950, {"C", "G", "T"}, "C", "G"),
    "rs1799963": (46761054, {"G", "A"}, 46739504, {"G", "A"}, "G", "A"),
    "rs1800562": (26093140, {"G", "A", "T"}, 26092912, {"G", "A", "T"}, "G", "A"),
    "rs1801133": (11856377, {"G", "A", "C", "T"}, 11796320, {"G", "A", "C", "T"}, "G", "A"),
    "rs3918290": (97915613, {"C", "A", "G", "T"}, 97450057, {"C", "A", "G", "T"}, "C", "T"),
    "rs4149056": (21331548, {"T", "A", "C"}, 21178614, {"T", "A", "C"}, "T", "C"),
    "rs4244285": (96541615, {"G", "A", "C", "T"}, 94781858, {"G", "A", "C", "T"}, "G", "A"),
    "rs429358": (45411940, {"T", "C"}, 44908683, {"T", "C"}, "T", "C"),
    "rs4988235": (136608645, {"G", "A", "C", "T"}, 135851075, {"G", "A", "C", "T"}, "G", "A"),
    # rs6025: GRCh37's reference base is T (the variant allele); GRCh38's is C.
    "rs6025": (169519048, {"T", "C", "A", "G"}, 169549810, {"C", "A", "G", "T"}, "C", "T"),
    "rs671": (112241765, {"G", "A"}, 111803961, {"G", "A"}, "G", "A"),
    "rs7412": (45412078, {"C", "T"}, 44908821, {"C", "T"}, "C", "T"),
    "rs9923231": (31107688, {"C", "A", "G", "T"}, 31096367, {"C", "A", "G", "T"}, "C", "T"),
}

# ClinVar accessions from the corrected accession table in reports/task-2-code-report.md
# (11 of the 14 old curated ids were wrong; constraints L2).
EXPECTED_CLINVAR = {
    "rs113993960": "VCV000007105",
    "rs1799945": "VCV000000010",
    "rs1799963": "VCV000013310",
    "rs1800562": "VCV000000009",
    "rs1801133": "VCV000003520",
    "rs3918290": "VCV000000432",
    "rs4149056": "VCV000037346",
    "rs4244285": "VCV000633856",
    "rs429358": "VCV000017864",
    "rs4988235": "VCV000007685",
    "rs6025": "VCV000000642",
    "rs671": "VCV000018390",
    "rs7412": "VCV000017848",
    "rs9923231": "VCV000002211",
}

FORBIDDEN_KEYS = {"coverage_state", "sample_observation", "assay_coverage", "curation_scope"}
INTERP_KEYS = {"category", "significance", "magnitude", "repute", "phenotype", "drug_response", "caveats"}
PROVENANCE_KEYS = {"source", "release", "accession", "url", "curation_mode", "retrieved_at"}


@pytest.fixture(scope="module")
def curation():
    return load_curation(DEFAULT_CURATION_PATH)


@pytest.fixture(scope="module")
def built(curation):
    payload, errors = build_kb(curation)
    assert errors == [], errors
    return payload


def walk(node, path=""):
    """Yield (path, key, value) for every dict entry in the document."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k, v
            yield from walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def has_error(errors, fragment):
    return any(fragment in e for e in errors)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def test_schema_version_and_top_level(built):
    assert built["schema_version"] == 2
    assert set(built) == {"schema_version", "manifest", "genes", "loci", "assemblies"}
    assert set(built["loci"]) == set(EXPECTED)


def test_every_locus_has_exactly_alt_count_interpretations(built):
    for rsid, locus in built["loci"].items():
        assert set(locus["interpretations"]) == {"0", "1", "2"}, rsid
        for count, interp in locus["interpretations"].items():
            assert set(interp) == INTERP_KEYS, (rsid, count)
            assert isinstance(interp["caveats"], list)
            assert 0.0 <= interp["magnitude"] <= 10.0


def test_no_per_sample_fields_anywhere(built):
    """CR-1: the KB describes loci, never one person's sample."""
    found = [(p, k) for p, k, _ in walk(built) if k in FORBIDDEN_KEYS]
    assert found == []


def test_unknown_evidence_is_null_never_a_placeholder(built):
    """CR-9: no gnomAD pLI of 0.0 placeholder; unknown values are null (T5: pLI and LOEUF are now imported)."""
    for rsid, locus in built["loci"].items():
        gnomad = locus["evidence"]["gnomad"]
        assert "pli" in gnomad and "loeuf" in gnomad
        for key in ("pli", "loeuf"):
            assert gnomad[key] is None or gnomad[key] > 0.0, (rsid, key)
    for section in ("genes", "loci"):
        for path, key, value in walk(built[section], f"/{section}"):
            if key in ("pli", "loeuf"):
                assert value != 0.0, path
            if section == "loci" and (path.endswith("/evidence") or "/evidence/" in path):
                assert value not in ("", "N/A", "unknown", "Unknown"), (path, key)
            if section == "genes" and isinstance(value, str):
                assert value.strip().lower() not in ("", "n/a", "none", "unknown"), (path, key)
                assert not value.lower().startswith("n/a"), (path, key, value)


def test_manually_curated_provenance_has_no_retrieval_time(built):
    """Curated values carry no retrieval time; machine-imported ones (T5) carry the capture's real one."""
    records = [(p, v) for p, k, v in walk(built) if k in ("provenance", "constraint_provenance") and v is not None]
    assert records, "expected provenance records in the KB"
    for path, prov in records:
        assert set(prov) == PROVENANCE_KEYS, path
        assert prov["curation_mode"] in ("manually_curated", "machine_imported"), path
        assert (prov["retrieved_at"] is None) == (prov["curation_mode"] == "manually_curated"), path


# ---------------------------------------------------------------------------
# Identity: ref/alt and positions (constraints L1, T2 allele table)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rsid", sorted(EXPECTED))
def test_locus_identity_matches_dbsnp_allele_table(built, rsid):
    spdi37, set37, spdi38, set38, ref, alt = EXPECTED[rsid]
    locus = built["loci"][rsid]
    assert locus["ref"] == ref
    assert locus["alt"] == alt, "alt must be the clinically relevant variant allele"
    assert {locus["ref"], locus["alt"]} <= set37
    assert {locus["ref"], locus["alt"]} <= set38
    assert locus["pos_grch37"] == spdi37 + 1
    assert locus["pos_grch38"] == spdi38 + 1


def test_rs6025_ref_alt_is_build_independent(built):
    """GRCh37's reference base T is the variant allele: ref/alt are not assembly bases."""
    locus = built["loci"]["rs6025"]
    assert (locus["ref"], locus["alt"]) == ("C", "T")


def test_indel_locus_declares_array_allele_codes(built):
    assert built["loci"]["rs113993960"]["allele_codes"] == {"D": "alt", "I": "ref"}
    assert all(
        built["loci"][r]["allele_codes"] is None for r in built["loci"] if r != "rs113993960"
    )


def test_clinvar_accessions_come_from_the_corrected_table(built):
    for rsid, accession in EXPECTED_CLINVAR.items():
        assert built["loci"][rsid]["evidence"]["clinvar"]["accession"] == accession


def test_apoe_component_roles(built):
    roles = {r: l["role"] for r, l in built["loci"].items()}
    assert roles["rs429358"] == roles["rs7412"] == "apoe_component"
    assert {r for r, v in roles.items() if v == "standard"} == set(EXPECTED) - {"rs429358", "rs7412"}


# ---------------------------------------------------------------------------
# Migration: alt-count semantics (complemented keys land on the right count)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rsid,count,fragment",
    [
        ("rs6025", "2", "Factor V Leiden homozygote"),  # old key AA (minus strand) -> plus TT
        ("rs6025", "1", "Factor V Leiden heterozygote"),  # old key AG
        ("rs9923231", "2", "High Warfarin sensitivity"),  # old key AA -> plus TT
        ("rs9923231", "1", "Intermediate Warfarin sensitivity"),  # old key AG -> plus CT
        ("rs113993960", "2", "ΔF508 homozygote"),  # old key DD
        ("rs113993960", "1", "heterozygote"),  # old key DI
        ("rs1801133", "2", "677TT"),
        ("rs4244285", "2", "Two CYP2C19*2 (rs4244285) alleles detected"),
        ("rs429358", "2", "ε4/ε4 homozygote"),
        ("rs7412", "2", "ε2/ε2"),
        ("rs3918290", "2", "Two DPYD*2A (rs3918290) alleles detected"),
        ("rs3918290", "1", "One DPYD*2A (rs3918290) allele detected"),
        ("rs4988235", "2", "Lactase persistent: Capable"),  # old key AA
        ("rs4988235", "1", "Tolerates dairy lactose well"),  # old key AG
        ("rs4988235", "0", "No MCM6/LCT -13910T allele detected"),  # old key GG
        ("rs671", "2", "ALDH2*2 homozygote"),
        ("rs671", "1", "ALDH2*2 heterozygote"),
        ("rs1799963", "2", "G20210A homozygote"),
        ("rs1799963", "1", "G20210A heterozygote"),
        ("rs4149056", "2", "Poor SLCO1B1 transporter function"),  # old key CC
        ("rs4149056", "1", "Intermediate SLCO1B1 function"),  # old key CT
    ],
)
def test_migrated_interpretation_sits_on_the_right_alt_count(built, rsid, count, fragment):
    assert fragment in built["loci"][rsid]["interpretations"][count]["phenotype"]


def test_count_zero_never_claims_normality(built):
    """AGENTS.md 4.1: 'No <allele> allele detected at this position', never 'normal'."""
    for rsid, locus in built["loci"].items():
        zero = locus["interpretations"]["0"]
        text = (zero["phenotype"] + " " + zero["significance"]).lower()
        assert "normal" not in text, rsid
        assert "wild-type" not in text and "wild type" not in text, rsid
        assert zero["category"] == "Not detected", rsid
        assert zero["magnitude"] == 0
        assert zero["repute"] == "Neutral", rsid
        assert zero["phenotype"].startswith("No "), rsid
        assert "allele detected at this position" in zero["phenotype"], rsid


def test_lactase_count_zero_is_an_absence_not_a_phenotype(built):
    """S3b-C-2: no -13910T allele does not establish lactase non-persistence (other persistence variants exist)."""
    zero = built["loci"]["rs4988235"]["interpretations"]["0"]
    assert zero["phenotype"] == (
        "No MCM6/LCT -13910T allele detected at this position. "
        "Lactase persistence from other variants is not excluded."
    )
    assert (zero["category"], zero["magnitude"], zero["repute"]) == ("Not detected", 0, "Neutral")
    assert "non-persistent" not in zero["phenotype"] and "Susceptible" not in zero["phenotype"]


def test_cyp2c19_states_one_snp_observation_and_assigns_no_metabolizer(built):
    """S5a-C-3: a single rs4244285 call cannot establish *1/*2 or *2/*2, so no metabolizer label is shown."""
    interps = built["loci"]["rs4244285"]["interpretations"]
    assert interps["1"]["phenotype"].startswith("One CYP2C19*2 (rs4244285) allele detected.")
    assert interps["2"]["phenotype"].startswith("Two CYP2C19*2 (rs4244285) alleles detected.")
    for count, interp in interps.items():
        text = interp["phenotype"] + " " + (interp["drug_response"] or "")
        assert not re.search(r"Metabolizer\s*\(|\*1/\*2|\*2/\*2", text), (count, text)
        assert not re.search(r"(Intermediate|Poor|Normal|Rapid|Ultrarapid) Metabolizer", text), (count, text)
    for count in ("1", "2"):
        assert "star-allele diplotyping" in interps[count]["phenotype"], count
    assert built["loci"]["rs4244285"]["limitation"] == INCOMPLETE_STAR_ALLELE_REFUSAL


def test_dpyd_states_one_snp_observation_and_assigns_no_deficiency_label(built):
    """CLEANUP-1 item 1 (same rule as S5a-C-3): one rs3918290 call cannot establish DPD activity."""
    interps = built["loci"]["rs3918290"]["interpretations"]
    assert interps["1"]["phenotype"].startswith("One DPYD*2A (rs3918290) allele detected.")
    assert interps["2"]["phenotype"].startswith("Two DPYD*2A (rs3918290) alleles detected.")
    for count in ("1", "2"):
        text = interps[count]["phenotype"] + " " + (interps[count]["drug_response"] or "")
        assert "Deficiency" not in text, (count, text)
        assert "other DPYD variants that this array does not test" in interps[count]["phenotype"], count


def test_apoe_wording_labels_relative_and_absolute_risk_apart(built):
    """S2-F1 review Minor: a relative multiple is never read as an absolute lifetime figure. No figure changes."""
    dips = built["genes"]["APOE"]["diplotypes"]
    assert "~12–15× relative risk (versus ε3/ε3)" in dips["e4/e4"]["phenotype"]
    expected = {
        "e3/e4": ("~3–4× relative risk (versus ε3/ε3)", "absolute lifetime risk ~25–35%"),
        "e2/e4": ("relative risk ~1.5–2× versus ε3/ε3", "absolute lifetime risk ~15–20%"),
        "e2/e3": ("~40–50% lower relative risk (versus ε3/ε3)", "absolute lifetime risk ~5–8%"),
    }
    for key, (relative, absolute) in expected.items():
        phenotype = dips[key]["phenotype"]
        assert relative in phenotype and absolute in phenotype, (key, phenotype)
        assert "elevated risk" not in phenotype and "lifetime risk)" not in phenotype, key
    # The figures themselves are untouched: they still sit in the caveats as written.
    assert "Relative risk: 3–4× Increased Risk" in dips["e3/e4"]["caveats"]
    assert "Lifetime risk: 25–35% lifetime Alzheimer's risk" in dips["e3/e4"]["caveats"]
    assert "Relative risk: 1.5–2× Intermediate Risk" in dips["e2/e4"]["caveats"]
    assert "Lifetime risk: 15–20% lifetime Alzheimer's risk" in dips["e2/e4"]["caveats"]
    assert built["loci"]["rs429358"]["interpretations"]["2"]["phenotype"] == (
        "APOE ε4/ε4 homozygote: ~12-15× relative risk (versus ε3/ε3) of late-onset Alzheimer's disease."
    )


def test_missing_interpretations_were_authored(built):
    for rsid in ("rs1799945", "rs113993960", "rs3918290", "rs1801133"):
        zero = built["loci"][rsid]["interpretations"]["0"]
        assert zero["category"] == "Not detected"
        assert zero["drug_response"] is None


# ---------------------------------------------------------------------------
# Genes
# ---------------------------------------------------------------------------
EXPECTED_MODELS = {
    "HFE": ("autosomal_recessive", True),
    "CFTR": ("autosomal_recessive", True),
    "APOE": ("risk_factor", False),
    "F5": ("risk_factor", False),
    "F2": ("risk_factor", False),
    "CYP2C19": ("pharmacogenomic", False),
    "VKORC1": ("pharmacogenomic", False),
    "SLCO1B1": ("pharmacogenomic", False),
    "DPYD": ("pharmacogenomic", False),
    "MTHFR": ("trait", False),
    "MCM6": ("trait", False),
    "ALDH2": ("trait", False),
}


def test_gene_inheritance_follows_the_owner_safe_classification(built):
    assert set(built["genes"]) == set(EXPECTED_MODELS)
    for gene, (model, mendelian) in EXPECTED_MODELS.items():
        inh = built["genes"][gene]["inheritance"]
        assert (inh["model"], inh["mendelian_disease"]) == (model, mendelian), gene
    assert built["genes"]["HFE"]["inheritance"]["penetrance"] == 0.2
    assert "236250" in built["genes"]["MTHFR"]["inheritance"]["disease"]
    for gene in built["genes"].values():
        if not gene["inheritance"]["mendelian_disease"]:
            assert gene["inheritance"]["penetrance"] is None


def test_every_locus_gene_exists_and_acmg_flag_is_hfe_only(built):
    for rsid, locus in built["loci"].items():
        assert locus["gene"] in built["genes"], rsid
    assert {g for g, v in built["genes"].items() if v["acmg_sf"]} == {"HFE"}


def test_gene_insights_are_curated_and_null_when_absent(built):
    assert built["genes"]["APOE"]["insights"]["uniprot_id"] == "P02649"
    assert built["genes"]["APOE"]["insights"]["provenance"]["curation_mode"] == "manually_curated"
    assert built["genes"]["MCM6"]["insights"] is None


def test_apoe_diplotypes(built):
    dips = built["genes"]["APOE"]["diplotypes"]
    assert set(dips) == {"e2/e2", "e2/e3", "e2/e4", "e3/e3", "e3/e4", "e4/e4"}
    for key, interp in dips.items():
        assert set(interp) == INTERP_KEYS, key
        assert any("predominantly European-ancestry cohorts" in c for c in interp["caveats"]), key
    assert "normal" not in dips["e3/e3"]["phenotype"].lower()
    assert "diplotypes" not in built["genes"]["HFE"]


def test_limitations_ride_on_the_locus(built):
    loci = built["loci"]
    assert loci["rs4244285"]["limitation"] == INCOMPLETE_STAR_ALLELE_REFUSAL
    assert loci["rs1800562"]["limitation"] == ACMG_SINGLE_LOCUS_CAVEAT
    assert loci["rs1799945"]["limitation"] == ACMG_SINGLE_LOCUS_CAVEAT
    assert "Single-variant test" in loci["rs4988235"]["limitation"]
    assert "more than 2,000" in loci["rs113993960"]["limitation"]
    assert "several CPIC-relevant DPYD variants" in loci["rs3918290"]["limitation"]
    for rsid in ("rs9923231", "rs4149056"):
        assert loci[rsid]["limitation"]


# ---------------------------------------------------------------------------
# Evidence tier and sufficiency rules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "stars,conflicting,tier",
    [
        (4, False, EvidenceTier.TIER_A),
        (3, False, EvidenceTier.TIER_A),
        (2, False, EvidenceTier.TIER_B),
        (1, False, EvidenceTier.TIER_C),
        (0, False, EvidenceTier.TIER_D),
        (None, False, EvidenceTier.TIER_D),
        (4, True, EvidenceTier.TIER_D),
        (1, True, EvidenceTier.TIER_D),
    ],
)
def test_derive_evidence_tier(stars, conflicting, tier):
    assert derive_evidence_tier(stars, conflicting) is tier


def test_derive_evidence_tier_rejects_impossible_stars():
    with pytest.raises(ValueError):
        derive_evidence_tier(5)


@pytest.mark.parametrize(
    "tier,expected",
    [
        (EvidenceTier.TIER_A, EvidenceSufficiency.SUFFICIENT),
        (EvidenceTier.TIER_B, EvidenceSufficiency.SUFFICIENT),
        (EvidenceTier.TIER_C, EvidenceSufficiency.INSUFFICIENT),
        (EvidenceTier.TIER_D, EvidenceSufficiency.INSUFFICIENT),
    ],
)
def test_derive_evidence_sufficiency(tier, expected):
    assert derive_evidence_sufficiency(tier) is expected


EXPECTED_TIERS = {
    # Mendelian-disease genes: ClinVar stars rule.
    "rs113993960": "Tier A", "rs1800562": "Tier B", "rs1799945": "Tier D",
    # Pharmacogenomic genes: CPIC level (all four gene-drug pairs are level A).
    "rs4244285": "Tier A", "rs9923231": "Tier A", "rs4149056": "Tier A", "rs3918290": "Tier A",
    # Risk-factor and trait genes: curated tier (constraints L7).
    "rs429358": "Tier A", "rs7412": "Tier A", "rs6025": "Tier A", "rs1799963": "Tier A",
    "rs1801133": "Tier C", "rs4988235": "Tier A", "rs671": "Tier A",
}


def test_locus_tier_source_follows_the_gene_inheritance_model(built):
    assert set(EXPECTED_TIERS) == set(built["loci"])
    for rsid, locus in built["loci"].items():
        assert locus["evidence_tier"] == EXPECTED_TIERS[rsid], rsid
        tier = EvidenceTier(locus["evidence_tier"])
        assert locus["evidence_sufficiency"] == derive_evidence_sufficiency(tier).value, rsid
        gene = built["genes"][locus["gene"]]["inheritance"]
        expected_source = (
            "clinvar_review" if gene["mendelian_disease"]
            else "cpic_level" if gene["model"] == "pharmacogenomic" else "curated"
        )
        assert locus["tier_source"] == expected_source, rsid
        if gene["mendelian_disease"]:
            clinvar = locus["evidence"]["clinvar"]
            conflicting = "conflicting" in clinvar["review_status"].lower()
            assert tier is derive_evidence_tier(clinvar["stars"], conflicting), rsid
            assert locus["tier_rationale"] is None and locus["tier_citation"] is None, rsid
        else:
            assert locus["tier_rationale"], rsid
            assert locus["tier_citation"], rsid
            assert not re.search(r"PMID|doi|10\.\d{4}", locus["tier_citation"], re.I), rsid
        if gene["model"] == "pharmacogenomic":
            assert locus["evidence"]["cpic"]["level"] == "A", rsid
            assert locus["evidence"]["cpic"]["provenance"]["curation_mode"] == "manually_curated"


@pytest.mark.parametrize(
    "level,tier",
    [("A", EvidenceTier.TIER_A), ("B", EvidenceTier.TIER_B), ("C", EvidenceTier.TIER_C),
     ("D", EvidenceTier.TIER_C), (None, EvidenceTier.TIER_D)],
)
def test_derive_tier_from_cpic_level(level, tier):
    assert derive_tier_from_cpic_level(level) is tier


def test_derive_tier_from_cpic_level_rejects_unknown_level():
    with pytest.raises(ValueError):
        derive_tier_from_cpic_level("E")


def test_qc_catches_non_clinvar_tier_without_citation_or_rationale(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs429358"]["tier"].pop("citation"))
    assert has_error(errors, "rs429358") and has_error(errors, "tier_citation")
    errors = mutated(curation, lambda d: d["loci"]["rs4244285"]["tier"].update(rationale=""))
    assert has_error(errors, "rs4244285") and has_error(errors, "tier_rationale")
    errors = mutated(curation, lambda d: d["loci"]["rs4244285"]["evidence"].pop("cpic"))
    assert has_error(errors, "rs4244285") and has_error(errors, "cpic")


def test_qc_rejects_a_citation_that_looks_like_a_pmid(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"]["tier"].update(citation="PMID 12345678"))
    assert has_error(errors, "rs671") and has_error(errors, "PMID")


def test_tier_source_values_per_locus(built):
    sources = {r: l["tier_source"] for r, l in built["loci"].items()}
    assert {r for r, v in sources.items() if v == "clinvar_review"} == {"rs113993960", "rs1800562", "rs1799945"}
    assert {r for r, v in sources.items() if v == "cpic_level"} == {"rs4244285", "rs9923231", "rs4149056", "rs3918290"}
    assert {r for r, v in sources.items() if v == "curated"} == {
        "rs429358", "rs7412", "rs6025", "rs1799963", "rs1801133", "rs4988235", "rs671"}


def test_qc_rejects_a_stray_curated_tier_on_a_pharmacogenomic_locus(curation):
    """A CPIC-level-A locus must never be silently built as a curated Tier D."""
    errors = mutated(curation, lambda d: d["loci"]["rs4244285"]["tier"].update(curated_tier="Tier D"))
    assert has_error(errors, "rs4244285") and has_error(errors, "curated_tier")


def test_build_selects_the_tier_source_by_model_not_by_key(curation):
    doc = copy.deepcopy(curation)
    doc["loci"]["rs4244285"]["tier"]["curated_tier"] = "Tier D"
    payload, errors = build_kb(doc)
    assert payload is None and errors


def test_qc_rejects_a_curated_locus_without_a_curated_tier(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"]["tier"].pop("curated_tier"))
    assert has_error(errors, "rs671") and has_error(errors, "curated_tier")


@pytest.mark.parametrize("block", ["clinvar", "gnomad", "hpa", "cpic"])
def test_malformed_evidence_block_is_a_qc_error_not_a_crash(curation, block):
    def mutate(d):
        d["loci"]["rs4244285"]["evidence"][block] = "x"

    errors = mutated(curation, mutate)
    assert has_error(errors, "rs4244285") and has_error(errors, block)


def test_qc_rejects_tier_basis_on_a_mendelian_locus(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs1800562"].update(
        tier={"curated_tier": "Tier A", "rationale": "x", "citation": "y"}))
    assert has_error(errors, "rs1800562") and has_error(errors, "ClinVar")


def test_indel_locus_is_stored_in_vcf_normalised_form(built):
    """Constraints L8: left-aligned with the anchor base, positions are the anchor's."""
    locus = built["loci"]["rs113993960"]
    assert (locus["ref"], locus["alt"]) == ("ATCT", "A")
    assert locus["pos_grch38"] == 117559590  # gnomAD 7-117559590-ATCT-A
    assert locus["pos_grch37"] == 117199644
    assert locus["allele_codes"] == {"D": "alt", "I": "ref"}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_build_is_byte_identical_across_runs(curation):
    first = render_kb(build_kb(copy.deepcopy(curation))[0])
    second = render_kb(build_kb(copy.deepcopy(curation))[0])
    assert first == second
    assert first.endswith("\n")


def test_manifest_has_no_wall_clock_and_a_canonical_sha(curation, built):
    manifest = built["manifest"]
    assert manifest["release"] == curation["release"]
    assert not any(re.search(r"date|time", k) for k in manifest)
    assert manifest["locus_count"] == len(built["loci"])
    canonical = json.dumps(
        {"genes": built["genes"], "loci": built["loci"], "assemblies": built["assemblies"]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert manifest["sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# QC rules: each mutation must be caught
# ---------------------------------------------------------------------------
def mutated(curation, fn):
    doc = copy.deepcopy(curation)
    fn(doc)
    return validate_curation(doc)


def test_qc_passes_on_the_real_curation(curation):
    assert validate_curation(curation) == []


def test_qc_catches_placeholder_pli(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"]["evidence"]["gnomad"].update(pli=0.0))
    assert has_error(errors, "rs671") and has_error(errors, "pLI")


def test_qc_catches_missing_interpretation(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"]["interpretations"].pop("1"))
    assert has_error(errors, "rs671") and has_error(errors, "interpretations")


def test_qc_catches_normality_wording_at_count_zero(curation):
    def mutate(d):
        d["loci"]["rs671"]["interpretations"]["0"]["phenotype"] = "Normal ALDH2 wild-type activity."

    errors = mutated(curation, mutate)
    assert has_error(errors, "rs671") and has_error(errors, "normal")


def test_qc_catches_retrieval_time_on_curated_provenance(curation):
    def mutate(d):
        d["loci"]["rs671"]["evidence"]["clinvar"]["provenance"]["retrieved_at"] = "2026-10-02T00:00:00Z"

    errors = mutated(curation, mutate)
    assert has_error(errors, "rs671") and has_error(errors, "retrieved_at")


def test_qc_catches_stars_that_disagree_with_review_status(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"]["evidence"]["clinvar"].update(stars=1))
    assert has_error(errors, "rs671") and has_error(errors, "stars")


def test_qc_catches_unknown_gene_and_bad_model(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"].update(gene="NOPE"))
    assert has_error(errors, "rs671") and has_error(errors, "gene")
    errors = mutated(curation, lambda d: d["genes"]["ALDH2"]["inheritance"].update(model="dominant-ish"))
    assert has_error(errors, "ALDH2") and has_error(errors, "model")


def test_qc_catches_missing_limitation_on_pharmacogenomic_locus(curation):
    def mutate(d):
        d["loci"]["rs9923231"].pop("limitation", None)
        d["loci"]["rs9923231"]["limitation"] = None

    errors = mutated(curation, mutate)
    assert has_error(errors, "rs9923231") and has_error(errors, "limitation")


def test_gnomad_source_label_matches_the_capture_composition(curation):
    """rs4988235 and rs9923231 captures hold a genome record only; their label must not say exome."""
    for rsid in ("rs4988235", "rs9923231"):
        source = curation["loci"][rsid]["evidence"]["gnomad"]["provenance"]["source"]
        assert "genome ac/an" in source and "exome" not in source, rsid


def test_qc_catches_wrong_acmg_flag(curation):
    errors = mutated(curation, lambda d: d["genes"]["HFE"].update(acmg_sf=False))
    assert has_error(errors, "HFE") and has_error(errors, "ACMG")


def test_qc_catches_identical_ref_alt(curation):
    errors = mutated(curation, lambda d: d["loci"]["rs671"].update(alt="G"))
    assert has_error(errors, "rs671") and has_error(errors, "ref")


def test_build_reports_qc_errors_instead_of_hiding_them(curation):
    bad = copy.deepcopy(curation)
    bad["loci"]["rs671"]["evidence"]["gnomad"]["pli"] = 0.0
    payload, errors = build_kb(bad)
    assert payload is None
    assert errors


# ---------------------------------------------------------------------------
# --verify-only (subprocess, temp files)
# ---------------------------------------------------------------------------
def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )


@pytest.fixture()
def good_kb(tmp_path, curation):
    path = tmp_path / "kb.json"
    path.write_text(render_kb(build_kb(curation)[0]), encoding="utf-8", newline="\n")
    return path


def test_verify_only_accepts_an_identical_file(good_kb):
    result = run_cli("--verify-only", "--kb-path", str(good_kb))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "QC errors: 0" in result.stdout
    assert result.stdout.strip().splitlines()[-1] == "KB up to date"


def test_verify_only_rejects_a_modified_file(good_kb):
    data = json.loads(good_kb.read_text(encoding="utf-8"))
    data["loci"]["rs671"]["evidence"]["gnomad"]["af"] = 0.5
    good_kb.write_text(render_kb(data), encoding="utf-8", newline="\n")
    result = run_cli("--verify-only", "--kb-path", str(good_kb))
    assert result.returncode == 1
    assert "KB differs" in result.stdout
    assert "rs671" in result.stdout


def test_verify_only_rejects_a_missing_file(tmp_path):
    result = run_cli("--verify-only", "--kb-path", str(tmp_path / "absent.json"))
    assert result.returncode == 1
    assert "not found" in result.stdout


def test_verify_only_fails_on_a_qc_error_with_the_real_count(tmp_path, good_kb, curation):
    bad = copy.deepcopy(curation)
    bad["loci"]["rs671"]["evidence"]["gnomad"]["pli"] = 0.0
    bad["loci"]["rs7412"]["interpretations"].pop("2")
    path = tmp_path / "curation.json"
    path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    result = run_cli("--verify-only", "--kb-path", str(good_kb), "--curation-path", str(path))
    assert result.returncode == 1
    assert "QC errors: 2" in result.stdout
    assert "100% PASSED" not in result.stdout


def test_default_run_writes_the_file_deterministically(tmp_path, curation):
    out = tmp_path / "kb.json"
    result = run_cli("--kb-path", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.read_text(encoding="utf-8") == render_kb(build_kb(curation)[0])


# ---------------------------------------------------------------------------
# T5: machine-imported evidence overlay and upstream cross-checks
# ---------------------------------------------------------------------------
UPSTREAM = ROOT / "tools" / "fixtures" / "upstream" / "real"
# Tier of every locus before the overlay existed (T4 build). Importing evidence must not move any of them.
TIERS_BEFORE_OVERLAY = {
    "rs113993960": "Tier A", "rs1799945": "Tier D", "rs1799963": "Tier A", "rs1800562": "Tier B",
    "rs1801133": "Tier C", "rs3918290": "Tier A", "rs4149056": "Tier A", "rs4244285": "Tier A",
    "rs429358": "Tier A", "rs4988235": "Tier A", "rs6025": "Tier A", "rs671": "Tier A",
    "rs7412": "Tier A", "rs9923231": "Tier A",
}


def write_curation(tmp_path, doc):
    path = tmp_path / "curation.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def cli_with_curation(tmp_path, good_kb, doc, *extra):
    path = write_curation(tmp_path, doc)
    return run_cli("--verify-only", "--kb-path", str(good_kb), "--curation-path", str(path), *extra)


def test_imported_evidence_is_machine_imported_with_the_captures_retrieval_time(built):
    for rsid, locus in built["loci"].items():
        clinvar = locus["evidence"]["clinvar"]
        meta = json.loads((UPSTREAM / "clinvar" / f"{rsid}.meta.json").read_text(encoding="utf-8"))
        prov = clinvar["provenance"]
        assert prov["curation_mode"] == "machine_imported", rsid
        assert (prov["retrieved_at"], prov["url"]) == (meta["retrieved_at"], meta["url"]), rsid
        assert prov["accession"].startswith(clinvar["accession"] + "."), rsid
        gnomad = locus["evidence"]["gnomad"]
        assert gnomad["provenance"]["curation_mode"] == "machine_imported", rsid
        assert gnomad["constraint_provenance"]["curation_mode"] == "machine_imported", rsid
        assert gnomad["pli"] is not None and gnomad["loeuf"] is not None, rsid


def test_values_without_an_adapter_stay_manually_curated(built, curation):
    """CPIC level, HPA tissues and gene insights have no adapter: they keep their curated provenance."""
    for rsid, locus in built["loci"].items():
        evidence = locus["evidence"]
        if evidence.get("hpa") is not None:
            assert evidence["hpa"]["provenance"]["curation_mode"] == "manually_curated", rsid
        if evidence.get("cpic") is not None:
            assert evidence["cpic"]["provenance"]["curation_mode"] == "manually_curated", rsid
            assert evidence["cpic"]["provenance"]["retrieved_at"] is None, rsid
    for symbol, gene in built["genes"].items():
        if gene["insights"] is not None:
            assert gene["insights"]["provenance"]["curation_mode"] == "manually_curated", symbol


def test_vep_and_dbsnp_evidence_is_imported(built):
    vep = built["loci"]["rs429358"]["evidence"]["vep"]
    assert vep["mane_select_refseq"] == "NM_000041.4" and vep["alphamissense_class"] == "likely_benign"
    assert built["loci"]["rs1799963"]["evidence"]["vep"]["alphamissense_class"] is None
    dbsnp = built["loci"]["rs113993960"]["evidence"]["dbsnp"]
    assert (dbsnp["pos_grch37"], dbsnp["pos_grch38"]) == (117199644, 117559590)
    assert dbsnp["provenance"]["curation_mode"] == "machine_imported"


def test_importing_evidence_changes_no_evidence_tier(built):
    """L7: imported ClinVar stars feed the tier only for Mendelian-disease genes; nothing else moves."""
    assert {r: l["evidence_tier"] for r, l in built["loci"].items()} == TIERS_BEFORE_OVERLAY


def test_mendelian_tier_follows_the_imported_stars(built):
    for rsid in ("rs113993960", "rs1799945", "rs1800562"):
        clinvar = built["loci"][rsid]["evidence"]["clinvar"]
        assert clinvar["provenance"]["curation_mode"] == "machine_imported"
        conflicting = "conflicting" in clinvar["review_status"]
        assert built["loci"][rsid]["evidence_tier"] == derive_evidence_tier(clinvar["stars"], conflicting).value


def test_clinvar_stays_evidence_only_for_non_mendelian_genes(built):
    """rs429358 (APOE, risk factor) has a 1-star conflicting ClinVar record yet keeps its curated Tier A."""
    locus = built["loci"]["rs429358"]
    assert locus["evidence"]["clinvar"]["stars"] == 1
    assert (locus["evidence_tier"], locus["tier_source"]) == ("Tier A", "curated")


def test_crosscheck_position_mismatch_fails_the_build(tmp_path, good_kb, curation):
    for key, build in (("pos_grch38", "GRCh38"), ("pos_grch37", "GRCh37")):
        bad = copy.deepcopy(curation)
        bad["loci"]["rs671"][key] += 1
        result = cli_with_curation(tmp_path, good_kb, bad)
        assert result.returncode == 1, key
        assert "rs671" in result.stdout and "dbSNP" in result.stdout and build in result.stdout


def test_crosscheck_allele_outside_dbsnps_set_fails_the_build(tmp_path, good_kb, curation):
    bad = copy.deepcopy(curation)
    bad["loci"]["rs671"]["alt"] = "C"
    result = cli_with_curation(tmp_path, good_kb, bad)
    assert result.returncode == 1
    assert "rs671" in result.stdout and "dbSNP" in result.stdout and "allele" in result.stdout


def test_crosscheck_indel_anchor_off_by_one_fails_the_build(tmp_path, good_kb, curation):
    bad = copy.deepcopy(curation)
    bad["loci"]["rs113993960"]["pos_grch38"] += 1
    result = cli_with_curation(tmp_path, good_kb, bad)
    assert result.returncode == 1
    assert "rs113993960" in result.stdout and "GRCh38" in result.stdout


def test_crosscheck_curated_clinvar_accession_must_equal_the_imported_one(tmp_path, good_kb, curation):
    """P2-011: a hand-typed accession that ClinVar's record for the locus does not carry fails the build."""
    bad = copy.deepcopy(curation)
    bad["loci"]["rs671"]["evidence"]["clinvar"]["accession"] = "VCV000009999"
    result = cli_with_curation(tmp_path, good_kb, bad)
    assert result.returncode == 1
    assert "QC errors: 1" in result.stdout
    assert "VCV000009999" in result.stdout and "VCV000018390" in result.stdout


def test_crosscheck_tampered_pinned_payload_fails_the_build(tmp_path, good_kb, curation):
    upstream = tmp_path / "real"
    shutil.copytree(UPSTREAM, upstream)
    target = upstream / "gnomad" / "rs671.json"
    target.write_bytes(target.read_bytes().replace(b'"ac":', b'"ac": ', 1))
    result = cli_with_curation(tmp_path, good_kb, curation, "--upstream-path", str(upstream))
    assert result.returncode == 1
    assert "gnomad/rs671.json" in result.stdout and "sha256" in result.stdout


def test_build_in_memory_reports_a_missing_payload_directory(curation, tmp_path):
    payload, errors = build_kb(curation, tmp_path / "absent")
    assert payload is None and has_error(errors, "not found")


def test_curation_only_build_is_reachable_through_an_explicit_parameter(curation):
    """upstream_root=None skips the overlay: curated provenance, null pLI, no vep/dbsnp blocks."""
    payload, errors = build_kb(curation, upstream_root=None)
    assert errors == []
    evidence = payload["loci"]["rs671"]["evidence"]
    assert evidence["clinvar"]["provenance"]["curation_mode"] == "manually_curated"
    assert evidence["gnomad"]["pli"] is None
    assert evidence["vep"] is None and evidence["dbsnp"] is None


def test_missing_per_variant_gnomad_capture_fails_the_build(tmp_path, good_kb, curation):
    """Review Minor 4: gnomAD refuses the rsid query for rs4244285 (L6). Without its per-variant capture the build
    must fail and name the rsid and the expected file, not fall back to the rsid file or the curated af."""
    upstream = tmp_path / "real"
    shutil.copytree(UPSTREAM, upstream)
    for suffix in (".json", ".meta.json"):
        (upstream / "gnomad" / f"rs4244285.10-94781859-G-A{suffix}").unlink()
    result = cli_with_curation(tmp_path, good_kb, curation, "--upstream-path", str(upstream))
    assert result.returncode == 1
    assert "QC errors: 1" in result.stdout
    assert "rs4244285" in result.stdout and "gnomad/rs4244285.10-94781859-G-A.json" in result.stdout


def test_missing_per_variant_capture_names_a_reason_on_the_adapter_model(tmp_path):
    """The ACL: the adapter recognises the refusal payload and hands over a named reason."""
    from tools.source_adapters import GNOMAD_REFUSAL_MULTIPLE_VARIANTS, UpstreamSnapshot

    upstream = tmp_path / "real"
    shutil.copytree(UPSTREAM, upstream)
    for suffix in (".json", ".meta.json"):
        (upstream / "gnomad" / f"rs3918290.1-97450058-C-A{suffix}").unlink()
    model = UpstreamSnapshot(upstream).gnomad_variant("rs3918290", "1-97450058-C-A")
    assert model.refusal == GNOMAD_REFUSAL_MULTIPLE_VARIANTS and model.af is None
    assert "gnomad/rs3918290.1-97450058-C-A.json" in model.reasons["af"]


def _drift(tmp_path, good_kb, curation, rsid, mutate):
    bad = copy.deepcopy(curation)
    mutate(bad["loci"][rsid]["evidence"])
    return cli_with_curation(tmp_path, good_kb, bad)


def test_drift_curated_gnomad_af_must_round_to_the_imported_one(tmp_path, good_kb, curation):
    result = _drift(tmp_path, good_kb, curation, "rs671", lambda e: e["gnomad"].__setitem__("af", 0.007037))
    assert result.returncode == 1
    assert "rs671" in result.stdout and "gnomad.af" in result.stdout


def test_drift_curated_clinvar_significance_must_equal_the_imported_one(tmp_path, good_kb, curation):
    result = _drift(tmp_path, good_kb, curation, "rs671", lambda e: e["clinvar"].__setitem__("significance", "Pathogenic"))
    assert result.returncode == 1
    assert "rs671" in result.stdout and "clinvar.significance" in result.stdout


def test_drift_curated_clinvar_review_status_and_stars_must_equal_the_imported_ones(tmp_path, good_kb, curation):
    def mutate(evidence):
        evidence["clinvar"]["review_status"] = "practice guideline"
        evidence["clinvar"]["stars"] = 4

    result = _drift(tmp_path, good_kb, curation, "rs671", mutate)
    assert result.returncode == 1
    assert "rs671" in result.stdout and "clinvar.review_status" in result.stdout and "clinvar.stars" in result.stdout


# ---------------------------------------------------------------------------
# Assemblies (karyogram K1, contract K-C1)
# ---------------------------------------------------------------------------
def test_assemblies_hold_both_builds_with_sources_copied_from_the_captures(built):
    assemblies = built["assemblies"]
    assert set(assemblies) == {"GRCh37", "GRCh38"}
    assert assemblies["GRCh37"]["ucsc"] == "hg19" and assemblies["GRCh38"]["ucsc"] == "hg38"
    assert list(assemblies["GRCh38"]["chromosomes"]) == [str(n) for n in range(1, 23)] + ["X", "Y"]
    assert assemblies["GRCh38"]["chromosomes"]["1"]["length"] == 248956422
    meta = json.loads((UPSTREAM / "ucsc" / "hg38.chromInfo.txt.gz.meta.json").read_text(encoding="utf-8"))
    source = assemblies["GRCh38"]["sources"][0]
    assert source == {
        "table": "chromInfo",
        "url": meta["url"],
        "retrieved": meta["retrieved_at"][:10],
        "sha256": meta["sha256_of_body"],
    }
    assert [s["table"] for s in assemblies["GRCh38"]["sources"]] == ["chromInfo", "cytoBand"]


def test_every_kb_locus_lies_within_its_chromosome_in_both_builds(built):
    for locus in built["loci"].values():
        for build, key in (("GRCh37", "pos_grch37"), ("GRCh38", "pos_grch38")):
            assert locus[key] <= built["assemblies"][build]["chromosomes"][locus["chrom"]]["length"]


def test_qc_fails_when_a_locus_position_exceeds_its_chromosome_length(curation, monkeypatch):
    real = UpstreamSnapshot.assembly

    def shrunk(self, build):
        geometry = real(self, build)
        chromosomes = dict(geometry.chromosomes)
        chrom = curation["loci"]["rs429358"]["chrom"]
        old = chromosomes[chrom]
        chromosomes[chrom] = replace(old, length=10, centromere_start=1, centromere_end=2)
        return replace(geometry, chromosomes=chromosomes)

    monkeypatch.setattr(UpstreamSnapshot, "assembly", shrunk)
    payload, errors = build_kb(curation)
    assert payload is None
    assert has_error(errors, "rs429358") and has_error(errors, "length")


def test_manifest_sha_changes_when_the_assemblies_change(curation, built, monkeypatch):
    real = UpstreamSnapshot.assembly

    def longer(self, build):
        geometry = real(self, build)
        chromosomes = dict(geometry.chromosomes)
        chromosomes["Y"] = replace(chromosomes["Y"], length=chromosomes["Y"].length + 1)
        return replace(geometry, chromosomes=chromosomes)

    monkeypatch.setattr(UpstreamSnapshot, "assembly", longer)
    other, errors = build_kb(curation)
    assert errors == []
    assert other["manifest"]["sha256"] != built["manifest"]["sha256"]


def test_verify_only_reports_an_assemblies_difference(good_kb):
    data = json.loads(good_kb.read_text(encoding="utf-8"))
    data["assemblies"]["GRCh37"]["chromosomes"]["1"]["length"] += 1
    good_kb.write_text(render_kb(data), encoding="utf-8", newline="\n")
    result = run_cli("--verify-only", "--kb-path", str(good_kb))
    assert result.returncode == 1
    assert "assemblies: GRCh37 differs in chromosomes" in result.stdout



IMPORTED_KEYS = ("alphamissense_class", "alphamissense_pathogenicity", "loeuf", "canonical_transcript")


def test_no_gene_insight_carries_a_value_the_pipeline_imports(built):
    for symbol, gene in built["genes"].items():
        ensembl = (gene["insights"] or {}).get("ensembl", {})
        assert not set(IMPORTED_KEYS) & set(ensembl), symbol


@pytest.mark.parametrize("key,value", [("loeuf", 0.44), ("alphamissense_class", "likely_benign"),
                                       ("alphamissense_pathogenicity", 0.1), ("canonical_transcript", "ENST1 (MANE Select)")])
def test_qc_rejects_a_curated_copy_of_an_imported_value(curation, key, value):
    errors = mutated(curation, lambda d: d["genes"]["HFE"]["insights"]["ensembl"].update({key: value}))
    assert has_error(errors, "HFE") and has_error(errors, key)


@pytest.mark.parametrize("text", ["N/A (3' UTR)", "n/a", "N/A", "None", "UNKNOWN", "none"])
def test_qc_rejects_a_placeholder_insight_string(curation, text):
    errors = mutated(curation, lambda d: d["genes"]["HFE"]["insights"]["ensembl"].update({"sift_prediction": text}))
    assert has_error(errors, "HFE") and has_error(errors, "placeholder")


@pytest.mark.parametrize("gnomad,fragment", [({"af": 1.5, "pli": None, "loeuf": None}, "af"),
                                             ({"af": -0.1, "pli": None, "loeuf": None}, "af"),
                                             ({"af": 0.1, "pli": -1.0, "loeuf": None}, "pli"),
                                             ({"af": 0.1, "pli": None, "loeuf": -0.2}, "loeuf")])
def test_imported_values_are_range_checked_after_the_overlay(gnomad, fragment):
    errors = _check_imported_ranges("rs1", gnomad)
    assert errors and fragment in errors[0]
    assert _check_imported_ranges("rs1", {"af": 0.0, "pli": 0.9, "loeuf": 0.5}) == []
    assert _check_imported_ranges("rs1", None) == []


def test_overlay_runs_the_range_check_on_the_finished_evidence(monkeypatch, curation):
    """S3-F1 Minor: _overlay_imported must call _check_imported_ranges, so an out-of-range import fails the build."""
    import tools.build_canonical_kb as builder

    seen = []

    def fake_check(rsid, gnomad):
        seen.append(rsid)
        return [f"{rsid}: sentinel range error"]

    monkeypatch.setattr(builder, "_check_imported_ranges", fake_check)
    kb, errors = build_kb(copy.deepcopy(curation))
    assert kb is None
    assert "rs6025" in seen
    assert any("sentinel range error" in e for e in errors), errors
