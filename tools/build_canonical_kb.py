#!/usr/bin/env python3
"""
Canonical knowledge-base build (schema v2, contract C2)
=======================================================
Reads the hand-edited curation file `tools/curation/kb_curation.json`, validates it, overlays the
machine-imported evidence from the pinned upstream payloads (`tools/fixtures/upstream/real/`, read
only through `tools/source_adapters.py`), adds the reference assembly geometry (`assemblies`, from the
pinned UCSC chromInfo and cytoBand tables), derives `evidence_tier` and `evidence_sufficiency` by rule,
and writes `web/src/knowledge-base.json`.

Imported values (ClinVar accession, review status, stars and significance; gnomAD allele frequency,
pLI and LOEUF; VEP MANE Select transcript and AlphaMissense; dbSNP positions) carry provenance
`machine_imported` with the capture's real `retrieved_at` and `url`. Curated values remain only where
no adapter value exists. QC cross-checks the curated positions, alleles and ClinVar accession against
the payloads and verifies the sha256 of every pinned payload.

The KB describes loci and what each alt-allele count means. Nothing in it depends on one
person's sample: observed genotype and coverage state are computed at analysis time.

The build is deterministic. The same curation file gives byte-identical JSON: no wall-clock
time, sorted keys, and a sha256 over the canonical JSON of `genes`, `loci` and `assemblies`.

Cardinal Scientific Rule:
"Absence of a finding must never imply absence of genetic risk."

Execution:
    python tools/build_canonical_kb.py                  # validate and write the KB
    python tools/build_canonical_kb.py --verify-only    # rebuild in memory, diff, exit 1 on any difference
    (--upstream-path DIR picks another pinned-payload directory)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.coverage_taxonomy import (  # noqa: E402
    ABSENCE_OF_FINDING_GUARDRAIL,
    ACMG_SINGLE_LOCUS_CAVEAT,
    INCOMPLETE_STAR_ALLELE_REFUSAL,
    CurationMode,
    EvidenceTier,
    derive_evidence_sufficiency,
    derive_evidence_tier,
    derive_tier_from_cpic_level,
)
from tools.source_adapters import REVIEW_STATUS_STARS, AdapterError, UpstreamSnapshot, esearch_uids  # noqa: E402
from tools.variome_models import GenotypeInterpretation  # noqa: E402

SCHEMA_VERSION = 2
DEFAULT_CURATION_PATH = PROJECT_ROOT / "tools" / "curation" / "kb_curation.json"
DEFAULT_KB_PATH = PROJECT_ROOT / "web" / "src" / "knowledge-base.json"
DEFAULT_UPSTREAM_ROOT = PROJECT_ROOT / "tools" / "fixtures" / "upstream" / "real"
BUILDS = (("GRCh37", "pos_grch37"), ("GRCh38", "pos_grch38"))

# ACMG Secondary Findings v3.2 Actionable Gene Panel (81 Genes)
ACMG_SF_V3_2_GENES = frozenset([
    "ACTA2", "ACTC1", "ACVRL1", "APC", "APOB", "ATP7B", "BAG3", "BMPR1A", "BRCA1",
    "BRCA2", "BTD", "CACNA1S", "CALM1", "CALM2", "CALM3", "CASQ2", "COL3A1",
    "DES", "DSC2", "DSG2", "DSP", "ENG", "FBN1", "FLNC", "GAA", "GLA", "HFE",
    "HNF1A", "KCNH2", "KCNJ2", "KCNQ1", "LDLR", "LMNA", "MAX", "MEN1", "MLH1",
    "MSH2", "MSH6", "MUTYH", "MYBPC3", "MYH11", "MYH7", "MYL2", "MYL3", "NF2",
    "OTC", "PALB2", "PCSK9", "PKP2", "PMS2", "PRKAG2", "PTEN", "RB1", "RBM20",
    "RET", "RPE65", "RYR1", "RYR2", "SCN5A", "SDHAF2", "SDHB", "SDHC", "SDHD",
    "SMAD3", "SMAD4", "STK11", "TGFBR1", "TGFBR2", "TMEM127", "TMEM43", "TNNC1",
    "TNNI3", "TNNT2", "TP53", "TPM1", "TRDN", "TSC1", "TSC2", "TTN", "VHL", "WT1",
])

# Curation files name shared limitation texts by constant instead of copying them.
LIMITATION_REFS = {
    "INCOMPLETE_STAR_ALLELE_REFUSAL": INCOMPLETE_STAR_ALLELE_REFUSAL,
    "ACMG_SINGLE_LOCUS_CAVEAT": ACMG_SINGLE_LOCUS_CAVEAT,
}
STAR_ALLELE_GENES = frozenset({"CYP2C19", "CYP2C9"})

INHERITANCE_MODELS = frozenset(
    {"autosomal_recessive", "autosomal_dominant", "risk_factor", "pharmacogenomic", "trait"}
)
ROLES = frozenset({"standard", "apoe_component"})
REPUTES = frozenset({"Good", "Bad", "Neutral"})
APOE_DIPLOTYPES = frozenset({"e2/e2", "e2/e3", "e2/e4", "e3/e3", "e3/e4", "e4/e4"})
PROVENANCE_INPUT_KEYS = frozenset({"source", "release", "accession", "url"})
INTERP_KEYS = frozenset({"category", "significance", "magnitude", "repute", "phenotype", "drug_response", "caveats"})
CPIC_LEVELS = frozenset({"A", "B", "C", "D"})
CURATED_TIERS = frozenset({"Tier A", "Tier B", "Tier C", "Tier D"})
# A citation names a guideline or paper. Identifiers typed from memory are refused.
CITATION_IDENTIFIER = re.compile(r"\bPMID\b|\bdoi\b|10\.\d{4,}", re.IGNORECASE)
NORMALITY_WORDING = re.compile(r"\bnormal\b|wild[- ]?type", re.IGNORECASE)
PRIVACY = {"local_analysis": True, "genomic_uploads": False, "variant_identifiers_transmitted": False}


# =============================================================================
# Load and validate (pure)
# =============================================================================
def load_curation(path: Path | str = DEFAULT_CURATION_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_provenance(spec: Any, where: str) -> list[str]:
    """Curated provenance names its source. It cannot carry a retrieval time or a curation mode."""
    if not isinstance(spec, dict):
        return [f"{where}: provenance missing"]
    errors = []
    if not isinstance(spec.get("source"), str) or not spec["source"]:
        errors.append(f"{where}: provenance needs a source")
    for key in spec:
        if key not in PROVENANCE_INPUT_KEYS:
            errors.append(
                f"{where}: provenance key {key!r} is not allowed "
                "(manually curated values carry no retrieved_at and no curation_mode of their own)"
            )
    return errors


def _check_interp(interp: Any, where: str, *, count_zero: bool = False) -> list[str]:
    if not isinstance(interp, dict):
        return [f"{where}: interpretation must be an object"]
    if set(interp) != INTERP_KEYS:
        return [f"{where}: interpretation keys must be exactly {sorted(INTERP_KEYS)}, found {sorted(interp)}"]
    errors = []
    for key in ("category", "significance", "phenotype"):
        if not isinstance(interp[key], str) or not interp[key].strip():
            errors.append(f"{where}: {key} must be a non-empty string")
    if not _is_number(interp["magnitude"]) or not 0.0 <= interp["magnitude"] <= 10.0:
        errors.append(f"{where}: magnitude must be a number in [0, 10]")
    if interp["repute"] not in REPUTES:
        errors.append(f"{where}: repute must be one of {sorted(REPUTES)}")
    if interp["drug_response"] is not None and not isinstance(interp["drug_response"], str):
        errors.append(f"{where}: drug_response must be a string or null")
    if not isinstance(interp["caveats"], list) or not all(isinstance(c, str) for c in interp["caveats"]):
        errors.append(f"{where}: caveats must be a list of strings")
    if count_zero:
        text = f"{interp['significance']} {interp['phenotype']}"
        match = NORMALITY_WORDING.search(text)
        if match:
            errors.append(
                f"{where}: count 0 wording asserts normality ({match.group(0)!r}); "
                "use 'No <allele> allele detected at this position'"
            )
    return errors


def _resolve_limitation(locus: dict[str, Any]) -> Optional[str]:
    if "limitation_ref" in locus:
        return LIMITATION_REFS.get(locus["limitation_ref"])
    return locus.get("limitation")


def _validate_gene(symbol: str, gene: Any) -> list[str]:
    if not isinstance(gene, dict):
        return [f"{symbol}: gene must be an object"]
    errors = []
    topic = gene.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        errors.append(f"{symbol}: topic must be a non-empty string (the plain-language result title)")
    elif topic != topic.strip():
        errors.append(f"{symbol}: topic has leading or trailing whitespace: {topic!r}")
    inh = gene.get("inheritance")
    if not isinstance(inh, dict):
        return [*errors, f"{symbol}: inheritance missing"]
    if inh.get("model") not in INHERITANCE_MODELS:
        errors.append(f"{symbol}: inheritance model {inh.get('model')!r} is not one of {sorted(INHERITANCE_MODELS)}")
    if not isinstance(inh.get("mendelian_disease"), bool):
        errors.append(f"{symbol}: mendelian_disease must be true or false")
    for key in ("disease", "omim"):
        if inh.get(key) is not None and not isinstance(inh[key], str):
            errors.append(f"{symbol}: inheritance {key} must be a string or null")
    pen = inh.get("penetrance")
    if pen is not None and (not _is_number(pen) or not 0.0 <= pen <= 1.0):
        errors.append(f"{symbol}: penetrance must be null or a number in [0, 1]")
    if not isinstance(gene.get("acmg_sf"), bool):
        errors.append(f"{symbol}: acmg_sf must be true or false")
    elif gene["acmg_sf"] != (symbol in ACMG_SF_V3_2_GENES):
        errors.append(f"{symbol}: acmg_sf {gene['acmg_sf']} disagrees with the ACMG SF v3.2 list")
    insights = gene.get("insights")
    if insights is not None:
        if not isinstance(insights, dict):
            errors.append(f"{symbol}: insights must be an object or null")
        else:
            errors.extend(_check_provenance(gene.get("insights_provenance"), f"{symbol}: insights"))
            errors.extend(_check_insights(insights, f"{symbol}: insights"))
    if "diplotypes" in gene:
        if symbol != "APOE":
            errors.append(f"{symbol}: only APOE carries diplotypes")
        diplotypes = gene["diplotypes"]
        if not isinstance(diplotypes, dict) or set(diplotypes) != APOE_DIPLOTYPES:
            errors.append(f"{symbol}: diplotypes must be exactly {sorted(APOE_DIPLOTYPES)}")
        else:
            for key, interp in diplotypes.items():
                errors.extend(_check_interp(interp, f"{symbol}: diplotype {key}"))
    elif symbol == "APOE":
        errors.append("APOE: diplotypes missing")
    return errors


IMPORTED_ONLY_INSIGHT_KEYS = ("alphamissense_class", "alphamissense_pathogenicity", "loeuf", "canonical_transcript")
PLACEHOLDER_STRINGS = ("n/a", "none", "unknown")


def _is_placeholder_string(value: str) -> bool:
    text = value.strip().lower()
    return text in PLACEHOLDER_STRINGS or text.startswith("n/a")


def _check_insights(node: Any, where: str) -> list[str]:
    """Insights carry no placeholder strings, and nothing the pipeline imports per locus (S3b-C-1)."""
    errors: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in IMPORTED_ONLY_INSIGHT_KEYS:
                errors.append(f"{where}/{key}: this value is imported per locus (VEP, gnomAD); a curated copy is not allowed")
            errors.extend(_check_insights(value, f"{where}/{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            errors.extend(_check_insights(value, f"{where}[{i}]"))
    elif isinstance(node, str) and _is_placeholder_string(node):
        errors.append(f"{where}: {node!r} is a placeholder; unknown values must be null")
    return errors


def _validate_evidence(rsid: str, evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"{rsid}: evidence missing"]
    errors = []
    for block in ("clinvar", "gnomad", "hpa", "cpic"):
        if evidence.get(block) is not None and not isinstance(evidence[block], dict):
            errors.append(f"{rsid}: evidence.{block} must be an object or null")
            evidence = {**evidence, block: None}
    clinvar = evidence.get("clinvar")
    if clinvar is not None:
        where = f"{rsid}: evidence.clinvar"
        if not re.fullmatch(r"VCV\d{9}", str(clinvar.get("accession", ""))):
            errors.append(f"{where}: accession must look like VCV000000000 (no version)")
        status = clinvar.get("review_status")
        stars = clinvar.get("stars")
        if status not in REVIEW_STATUS_STARS:
            errors.append(f"{where}: unknown review_status {status!r}")
        elif stars != REVIEW_STATUS_STARS[status]:
            errors.append(f"{where}: stars {stars!r} disagree with review_status {status!r} ({REVIEW_STATUS_STARS[status]})")
        if not isinstance(clinvar.get("significance"), str) or not clinvar["significance"]:
            errors.append(f"{where}: significance must be a non-empty string")
        errors.extend(_check_provenance(clinvar.get("provenance"), where))
    gnomad = evidence.get("gnomad")
    if gnomad is not None:
        where = f"{rsid}: evidence.gnomad"
        af = gnomad.get("af")
        if af is not None and (not _is_number(af) or not 0.0 <= af <= 1.0):
            errors.append(f"{where}: af must be null or a number in [0, 1]")
        for key in ("pli", "loeuf"):
            value = gnomad.get(key)
            if value is None:
                continue
            if not _is_number(value) or value < 0:
                errors.append(f"{where}: {key} must be null or a non-negative number")
            elif value == 0.0:
                errors.append(f"{where}: {key} of 0.0 is a placeholder; unknown values must be null (gnomAD pLI)")
            elif key == "pli" and value > 1.0:
                errors.append(f"{where}: pli must be in (0, 1]")
        errors.extend(_check_provenance(gnomad.get("provenance"), where))
    hpa = evidence.get("hpa")
    if hpa is not None:
        where = f"{rsid}: evidence.hpa"
        if not isinstance(hpa.get("tissues"), dict) or not isinstance(hpa.get("subcellular"), list):
            errors.append(f"{where}: tissues must be an object and subcellular a list")
        errors.extend(_check_provenance(hpa.get("provenance"), where))
    return errors


def tier_source_for(gene: Any) -> Optional[str]:
    """Contract L7: the tier source is a function of the gene's inheritance model, never of which keys exist."""
    inh = gene.get("inheritance") if isinstance(gene, dict) else None
    if not isinstance(inh, dict):
        return None
    if inh.get("mendelian_disease") is True:
        return "clinvar_review"
    return "cpic_level" if inh.get("model") == "pharmacogenomic" else "curated"


def _validate_tier_basis(rsid: str, locus: dict[str, Any], source: Optional[str]) -> list[str]:
    """The tier block must match the source the gene model dictates."""
    if source is None:
        return []
    basis = locus.get("tier")
    evidence = locus.get("evidence") if isinstance(locus.get("evidence"), dict) else {}
    if source == "clinvar_review":
        if basis is not None:
            return [f"{rsid}: Mendelian-disease loci take their tier from ClinVar stars; remove the tier block"]
        return [] if isinstance(evidence.get("clinvar"), dict) else [f"{rsid}: Mendelian-disease locus needs ClinVar evidence"]
    if not isinstance(basis, dict):
        return [f"{rsid}: tier_rationale and tier_citation required (non-ClinVar tier): add a tier block"]
    errors = []
    allowed = {"rationale", "citation"} | ({"curated_tier"} if source == "curated" else set())
    for key in sorted(set(basis) - allowed):
        errors.append(f"{rsid}: tier block key {key!r} does not belong to a {source} tier (gene model decides the source)")
    for key, label in (("rationale", "tier_rationale"), ("citation", "tier_citation")):
        if not isinstance(basis.get(key), str) or not basis[key].strip():
            errors.append(f"{rsid}: {label} is required for a non-ClinVar tier")
    citation = basis.get("citation")
    if isinstance(citation, str) and CITATION_IDENTIFIER.search(citation):
        errors.append(f"{rsid}: tier_citation must name the guideline or paper, not a PMID or DOI")
    if source == "cpic_level":
        cpic = evidence.get("cpic")
        if not isinstance(cpic, dict) or cpic.get("level") not in CPIC_LEVELS | {None}:
            errors.append(f"{rsid}: pharmacogenomic locus needs evidence.cpic with level A, B, C, D or null")
        else:
            errors.extend(_check_provenance(cpic.get("provenance"), f"{rsid}: evidence.cpic"))
            if not isinstance(cpic.get("drug"), str) or not cpic["drug"]:
                errors.append(f"{rsid}: evidence.cpic needs a drug")
    elif basis.get("curated_tier") not in CURATED_TIERS:
        errors.append(f"{rsid}: curated_tier must be one of {sorted(CURATED_TIERS)}")
    return errors


def _validate_locus(rsid: str, locus: Any, genes: dict[str, Any]) -> list[str]:
    if not isinstance(locus, dict):
        return [f"{rsid}: locus must be an object"]
    errors = []
    if not re.fullmatch(r"rs\d+", rsid):
        errors.append(f"{rsid}: rsid must look like rs123")
    gene_symbol = locus.get("gene")
    gene = genes.get(gene_symbol)
    if gene is None:
        errors.append(f"{rsid}: gene {gene_symbol!r} is not in genes")
    if not isinstance(locus.get("chrom"), str) or not locus["chrom"]:
        errors.append(f"{rsid}: chrom must be a non-empty string")
    for key in ("pos_grch37", "pos_grch38"):
        value = locus.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"{rsid}: {key} must be a positive integer (1-based)")
    ref, alt = locus.get("ref"), locus.get("alt")
    for key, value in (("ref", ref), ("alt", alt)):
        if not isinstance(value, str) or not re.fullmatch(r"[ACGT]+", value):
            errors.append(f"{rsid}: {key} must be a plus-strand sequence of A/C/G/T")
    if isinstance(ref, str) and ref == alt:
        errors.append(f"{rsid}: ref and alt must differ")
    codes = locus.get("allele_codes")
    if codes is not None and (
        not isinstance(codes, dict) or set(codes) != {"D", "I"} or not set(codes.values()) <= {"ref", "alt"}
    ):
        errors.append(f"{rsid}: allele_codes must be null or map D and I to ref/alt")
    role = locus.get("role")
    if role not in ROLES:
        errors.append(f"{rsid}: role must be one of {sorted(ROLES)}")
    elif (role == "apoe_component") != (gene_symbol == "APOE"):
        errors.append(f"{rsid}: role apoe_component belongs to APOE loci only (gene {gene_symbol!r}, role {role!r})")

    interps = locus.get("interpretations")
    if not isinstance(interps, dict) or set(interps) != {"0", "1", "2"}:
        found = sorted(interps) if isinstance(interps, dict) else interps
        errors.append(f"{rsid}: interpretations must be exactly 0, 1, 2 (found {found})")
    else:
        for count in ("0", "1", "2"):
            errors.extend(_check_interp(interps[count], f"{rsid}: interpretation {count}", count_zero=count == "0"))

    errors.extend(_validate_evidence(rsid, locus.get("evidence")))
    source = tier_source_for(gene)
    errors.extend(_validate_tier_basis(rsid, locus, source))

    if ("limitation_ref" in locus) == ("limitation" in locus):
        errors.append(f"{rsid}: give exactly one of limitation or limitation_ref")
    elif "limitation_ref" in locus and locus["limitation_ref"] not in LIMITATION_REFS:
        errors.append(f"{rsid}: unknown limitation_ref {locus['limitation_ref']!r}")
    else:
        limitation = _resolve_limitation(locus)
        if limitation is not None and not isinstance(limitation, str):
            errors.append(f"{rsid}: limitation must be a string or null")
        elif isinstance(gene, dict) and isinstance(gene.get("inheritance"), dict):
            inh = gene["inheritance"]
            if (inh.get("model") == "pharmacogenomic" or inh.get("mendelian_disease") is True) and not limitation:
                errors.append(f"{rsid}: limitation is required for pharmacogenomic and Mendelian-disease loci")
            if gene.get("acmg_sf") is True and limitation != ACMG_SINGLE_LOCUS_CAVEAT:
                errors.append(f"{rsid}: ACMG SF locus must carry the ACMG single-locus caveat")
            if gene_symbol in STAR_ALLELE_GENES and limitation != INCOMPLETE_STAR_ALLELE_REFUSAL:
                errors.append(f"{rsid}: star-allele locus must carry INCOMPLETE_STAR_ALLELE_REFUSAL")
    return errors


def validate_curation(curation: Any) -> list[str]:
    """Return every QC error in the curation file (empty list when it is clean)."""
    if not isinstance(curation, dict):
        return ["curation file must be a JSON object"]
    errors = []
    for key in ("release", "acmg_sf_version"):
        if not isinstance(curation.get(key), str) or not curation[key]:
            errors.append(f"{key} must be a non-empty string (a fixed value, never the clock)")
    genes, loci = curation.get("genes"), curation.get("loci")
    if not isinstance(genes, dict) or not genes:
        errors.append("genes must be a non-empty object")
        genes = {}
    if not isinstance(loci, dict) or not loci:
        errors.append("loci must be a non-empty object")
        loci = {}
    for symbol, gene in genes.items():
        errors.extend(_validate_gene(symbol, gene))
    for rsid, locus in loci.items():
        errors.extend(_validate_locus(rsid, locus, genes))
    return errors


# =============================================================================
# Build (pure)
# =============================================================================
def _provenance(spec: dict[str, Any]) -> dict[str, Any]:
    """Expand a curated provenance (contract C2). Curated values were not retrieved, so no timestamp."""
    return {
        "source": spec["source"],
        "release": spec.get("release"),
        "accession": spec.get("accession"),
        "url": spec.get("url"),
        "curation_mode": CurationMode.MANUALLY_CURATED.value,
        "retrieved_at": None,
    }


def _interp(raw: dict[str, Any]) -> dict[str, Any]:
    return GenotypeInterpretation(**raw).to_dict()


def _build_gene(gene: dict[str, Any]) -> dict[str, Any]:
    inh = gene["inheritance"]
    out: dict[str, Any] = {
        "topic": gene["topic"],
        "inheritance": {
            "model": inh["model"],
            "mendelian_disease": inh["mendelian_disease"],
            "disease": inh.get("disease"),
            "omim": inh.get("omim"),
            "penetrance": inh.get("penetrance"),
        },
        "acmg_sf": gene["acmg_sf"],
        "insights": None,
    }
    if gene.get("insights") is not None:
        out["insights"] = {**gene["insights"], "provenance": _provenance(gene["insights_provenance"])}
    if "diplotypes" in gene:
        out["diplotypes"] = {key: _interp(raw) for key, raw in gene["diplotypes"].items()}
    return out


def _build_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    clinvar = evidence.get("clinvar")
    out["clinvar"] = None if clinvar is None else {
        "accession": clinvar["accession"],
        "review_status": clinvar["review_status"],
        "stars": clinvar["stars"],
        "significance": clinvar["significance"],
        "provenance": _provenance(clinvar["provenance"]),
    }
    gnomad = evidence.get("gnomad")
    out["gnomad"] = None if gnomad is None else {
        "af": gnomad.get("af"),
        "pli": gnomad.get("pli"),
        "loeuf": gnomad.get("loeuf"),
        "provenance": _provenance(gnomad["provenance"]),
    }
    hpa = evidence.get("hpa")
    out["hpa"] = None if hpa is None else {
        "tissues": hpa["tissues"],
        "subcellular": hpa["subcellular"],
        "provenance": _provenance(hpa["provenance"]),
    }
    cpic = evidence.get("cpic")
    if cpic is not None:
        out["cpic"] = {"level": cpic["level"], "drug": cpic["drug"], "provenance": _provenance(cpic["provenance"])}
    return out


def _decimal_places(value: float) -> int:
    """Decimal places of a curated number as written (its shortest repr, so 0.14229 has 5)."""
    return max(0, -Decimal(repr(value)).as_tuple().exponent)


def _af_agrees(curated: float, imported: float) -> bool:
    """The imported af, rounded half-up to the curated value's decimal places, equals the curated value."""
    places = _decimal_places(curated)
    rounded = Decimal(repr(imported)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return rounded == Decimal(repr(curated))


def _clinvar_drift(rsid: str, curated: dict[str, Any], imported: Any) -> list[str]:
    """QC errors for each curated ClinVar field that is present and differs from the imported record."""
    errors = []
    for field in ("review_status", "stars", "significance"):
        if curated.get(field) is not None and curated[field] != getattr(imported, field):
            errors.append(f"{rsid}: curated clinvar.{field} {curated[field]!r} differs from the imported "
                          f"{getattr(imported, field)!r}")
    return errors


def _capture_problems(root: Path, rsid: str, gene: str, variant_id: str) -> list[str]:
    """QC errors for every capture a curated locus needs that is missing or empty (S3b-C-5).

    The expected files come from the locus alone: dbSNP, ClinVar, VEP, the gnomAD variant (its per-variant
    file or the rsid file) and the gnomAD constraint of the gene. A missing or empty file would otherwise
    switch its cross-check off without a word.
    """
    clinvar_candidates = (f"clinvar/{rsid}.json",)
    esearch_path = root / f"clinvar/{rsid}.esearch.json"
    if esearch_path.is_file():
        try:
            if not esearch_uids(esearch_path.read_bytes()):
                clinvar_candidates = (f"clinvar/{rsid}.esearch.json",)
        except Exception:
            pass

    expected = [
        (f"dbsnp/{rsid}.json",),
        clinvar_candidates,
        (f"ensembl/{rsid}.json",),
        (f"gnomad/{rsid}.{variant_id}.json", f"gnomad/{rsid}.json"),
        (f"gnomad/constraint_{gene}.json",),
    ]
    errors = []
    for candidates in expected:
        found = [rel for rel in candidates if (root / rel).is_file()]
        if not found:
            errors.append(f"{rsid}: the pinned capture {' or '.join(candidates)} is missing, so its cross-check cannot run")
            continue
        try:
            body = json.loads((root / found[0]).read_bytes())
        except ValueError:
            continue  # unreadable JSON is reported by the adapter that parses it
        if not body:
            errors.append(f"{rsid}: the pinned capture {found[0]} is empty, so its cross-check cannot run")
    return errors


def _overlay_imported(rsid: str, locus: dict[str, Any], evidence: dict[str, Any], snapshot: UpstreamSnapshot) -> list[str]:
    """Replace curated evidence with adapter values where an adapter has them, and cross-check the rest.

    Mutates `evidence`. Returns QC errors: curated positions or alleles that dbSNP disagrees with (L1, L8),
    a curated ClinVar accession that differs from the imported one (P2-011), a gnomAD capture for another
    variant or gene, or a payload an adapter refuses.
    """
    errors: list[str] = []
    ref, alt, gene = locus["ref"], locus["alt"], locus["gene"]
    variant_id = f"{locus['chrom']}-{locus['pos_grch38']}-{ref}-{alt}"
    errors.extend(_capture_problems(snapshot.root, rsid, gene, variant_id))
    if errors:  # an adapter cannot read a capture that is not there or has no content
        return errors
    try:
        dbsnp = snapshot.dbsnp(rsid)
        if dbsnp is not None:
            clean = True
            for build, key in BUILDS:
                reason = dbsnp.check_locus(build, locus[key], ref, alt)
                if reason is not None:
                    clean = False
                    errors.append(f"{rsid}: curated locus disagrees with dbSNP: {reason}")
            if clean:
                evidence["dbsnp"] = {
                    **{key: dbsnp.placements[build].locate(ref, alt) for build, key in BUILDS},
                    "provenance": dbsnp.provenance.to_dict(),
                }

        curated_clinvar = evidence.get("clinvar")
        clinvar = snapshot.clinvar(rsid, locus["pos_grch38"], ref, alt)
        if clinvar is None:
            if curated_clinvar is not None:
                errors.append(f"{rsid}: no ClinVar record matches the locus alleles, so the curated accession "
                              f"{curated_clinvar['accession']} cannot be verified")
        elif clinvar.accession is None or clinvar.significance is None:
            errors.append(f"{rsid}: selected ClinVar record is incomplete: {clinvar.reasons}")
        elif curated_clinvar is not None and curated_clinvar["accession"] != clinvar.accession:
            errors.append(f"{rsid}: curated ClinVar accession {curated_clinvar['accession']} differs from the "
                          f"imported {clinvar.accession} ({clinvar.selected_by})")
        elif curated_clinvar is not None and (drift := _clinvar_drift(rsid, curated_clinvar, clinvar)):
            errors.extend(drift)
        else:
            evidence["clinvar"] = {
                "accession": clinvar.accession,
                "review_status": clinvar.review_status,
                "stars": clinvar.stars,
                "significance": clinvar.significance,
                "provenance": clinvar.provenance.to_dict(),
            }

        variant = snapshot.gnomad_variant(rsid, variant_id)
        constraint = snapshot.constraint(gene)
        if variant is not None and variant.refusal is not None:
            errors.append(f"{rsid}: gnomAD af cannot be imported: {variant.reasons['af']}")
            variant = None
        if variant is not None and variant.variant_id != variant_id:
            errors.append(f"{rsid}: gnomAD capture is for {variant.variant_id}, the locus is {variant_id}")
            variant = None
        if constraint is not None and constraint.symbol != gene:
            errors.append(f"{rsid}: gnomAD constraint capture is for {constraint.symbol}, the locus gene is {gene}")
            constraint = None
        curated_af = (evidence.get("gnomad") or {}).get("af")
        if variant is not None and variant.af is None and curated_af is not None:
            errors.append(f"{rsid}: gnomAD af is unavailable ({variant.reasons.get('af')}) but curation holds "
                          f"gnomad.af {curated_af!r}, which would stand unchecked")
        if variant is not None and variant.af is not None and curated_af is not None:
            if not _af_agrees(curated_af, variant.af):
                errors.append(f"{rsid}: curated gnomad.af {curated_af!r} differs from the imported {variant.af!r} "
                              f"(rounded half-up to the curated {_decimal_places(curated_af)} places)")
        gnomad = dict(evidence.get("gnomad") or {"af": None, "pli": None, "loeuf": None, "provenance": None})
        gnomad["constraint_provenance"] = None
        if variant is not None and variant.af is not None:
            gnomad["af"], gnomad["provenance"] = variant.af, variant.provenance.to_dict()
        if constraint is not None and (constraint.pli is not None or constraint.loeuf is not None):
            gnomad["pli"], gnomad["loeuf"] = constraint.pli, constraint.loeuf
            gnomad["constraint_provenance"] = constraint.provenance.to_dict()
        if evidence.get("gnomad") is not None or gnomad["constraint_provenance"] or gnomad["provenance"]:
            evidence["gnomad"] = gnomad

        vep = snapshot.vep(rsid, gene, ref, alt)
        if vep is not None:
            evidence["vep"] = {
                "mane_select_ensembl": vep.mane_select_ensembl,
                "mane_select_refseq": vep.mane_select_refseq,
                "alphamissense_class": vep.alphamissense_class,
                "alphamissense_score": vep.alphamissense_score,
                "provenance": vep.provenance.to_dict(),
            }
    except (AdapterError, ValueError) as exc:
        errors.append(f"{rsid}: upstream payload cannot be imported: {exc}")
    errors.extend(_check_imported_ranges(rsid, evidence.get("gnomad")))
    return errors


def _check_imported_ranges(rsid: str, gnomad: Optional[dict[str, Any]]) -> list[str]:
    """The finished KB obeys the same range rules as curation: af in [0, 1], pLI and LOEUF non-negative (S3b-C-8)."""
    if not gnomad:
        return []
    errors = []
    af = gnomad.get("af")
    if af is not None and (not _is_number(af) or not 0.0 <= af <= 1.0):
        errors.append(f"{rsid}: imported gnomad.af {af!r} is outside [0, 1]")
    for key in ("pli", "loeuf"):
        value = gnomad.get(key)
        if value is not None and (not _is_number(value) or value < 0):
            errors.append(f"{rsid}: imported gnomad.{key} {value!r} is negative or not a number")
    return errors


def _build_locus(
    rsid: str, locus: dict[str, Any], gene: dict[str, Any], snapshot: UpstreamSnapshot
) -> tuple[dict[str, Any], list[str]]:
    evidence = _build_evidence(locus["evidence"])
    evidence.setdefault("dbsnp", None)
    evidence.setdefault("vep", None)
    errors = _overlay_imported(rsid, locus, evidence, snapshot)
    basis = locus.get("tier")
    source = tier_source_for(gene)
    if source == "clinvar_review":  # Mendelian-disease gene: ClinVar review stars (imported where available)
        clinvar = evidence["clinvar"]
        tier = derive_evidence_tier(clinvar["stars"], "conflicting" in clinvar["review_status"].lower())
    elif source == "curated":  # risk_factor / trait gene: curated tier. ClinVar stays evidence only (L7)
        tier = EvidenceTier(basis["curated_tier"])
    else:  # pharmacogenomic gene: CPIC level
        tier = derive_tier_from_cpic_level(evidence["cpic"]["level"])
    return {
        "rsid": rsid,
        "gene": locus["gene"],
        "chrom": locus["chrom"],
        "pos_grch37": locus["pos_grch37"],
        "pos_grch38": locus["pos_grch38"],
        "ref": locus["ref"],
        "alt": locus["alt"],
        "allele_codes": locus["allele_codes"],
        "interpretations": {count: _interp(locus["interpretations"][count]) for count in ("0", "1", "2")},
        "evidence": evidence,
        "evidence_tier": tier.value,
        "evidence_sufficiency": derive_evidence_sufficiency(tier).value,
        "tier_source": source,
        "tier_rationale": basis["rationale"] if basis else None,
        "tier_citation": basis["citation"] if basis else None,
        "limitation": _resolve_limitation(locus),
        "role": locus["role"],
    }, errors


def _assembly_dict(geometry: Any) -> dict[str, Any]:
    """K-C1 `Assembly` from the adapter's model. Sources are copied from the capture metadata."""
    return {
        "ucsc": geometry.ucsc,
        "sources": [
            {
                "table": source.accession,
                "url": source.url,
                "retrieved": source.retrieved_at[:10],
                "sha256": source.sha256,
            }
            for source in geometry.sources
        ],
        "chromosomes": {
            name: {"length": chrom.length, "centromere": [chrom.centromere_start, chrom.centromere_end]}
            for name, chrom in geometry.chromosomes.items()
        },
    }


def check_locus_bounds(loci: dict[str, Any], assemblies: dict[str, Any]) -> list[str]:
    """QC errors for every locus whose position lies outside its chromosome in the matching build."""
    errors = []
    for rsid, locus in sorted(loci.items()):
        for build, key in BUILDS:
            chromosome = assemblies[build]["chromosomes"].get(locus["chrom"])
            if chromosome is None:
                errors.append(f"{rsid}: chromosome {locus['chrom']!r} is not in the {build} assembly")
            elif locus[key] > chromosome["length"]:
                errors.append(f"{rsid}: {key} {locus[key]} exceeds the {build} length {chromosome['length']} "
                              f"of chromosome {locus['chrom']}")
    return errors


def build_kb(
    curation: dict[str, Any], upstream_root: Path | str = DEFAULT_UPSTREAM_ROOT
) -> tuple[Optional[dict[str, Any]], list[str]]:
    """Build the KB document in memory. Returns (None, errors) when QC finds any error.

    `upstream_root` holds the pinned upstream payloads. Their sha256 is verified first; a tampered
    payload is a QC error and nothing is imported from it. It is required: `assemblies` comes only from the
    pinned UCSC tables and the web loader rejects a KB without it, so a curation-only build (None) raises
    `ValueError` instead of returning a KB that cannot load.
    """
    if upstream_root is None:
        raise ValueError(
            "build_kb: upstream_root is required. The KB's assemblies come only from the pinned UCSC payloads, "
            "so a build without them would omit assemblies and the web loader would reject it"
        )
    errors = validate_curation(curation)
    if errors:
        return None, errors
    snapshot = UpstreamSnapshot(upstream_root)
    errors = snapshot.verify_integrity()
    if errors:
        return None, errors
    genes = {symbol: _build_gene(curation["genes"][symbol]) for symbol in sorted(curation["genes"])}
    loci = {}
    for rsid in sorted(curation["loci"]):
        locus = curation["loci"][rsid]
        loci[rsid], locus_errors = _build_locus(rsid, locus, curation["genes"][locus["gene"]], snapshot)
        errors.extend(locus_errors)
    try:
        assemblies = {build: _assembly_dict(snapshot.assembly(build)) for build, _ in BUILDS}
    except AdapterError as exc:
        errors.append(f"assemblies: UCSC geometry cannot be imported: {exc}")
    else:
        errors.extend(check_locus_bounds(loci, assemblies))
    if errors:
        return None, errors
    sections = {"genes": genes, "loci": loci, "assemblies": assemblies}
    canonical = json.dumps(sections, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    manifest = {
        "release": curation["release"],
        "acmg_sf_version": curation["acmg_sf_version"],
        "locus_count": len(loci),
        "gene_count": len(genes),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "guardrail": ABSENCE_OF_FINDING_GUARDRAIL,
        "privacy": dict(PRIVACY),
    }
    return {"schema_version": SCHEMA_VERSION, "manifest": manifest, **sections}, []


def render_kb(payload: dict[str, Any]) -> str:
    """The one serialization of the KB: sorted keys, 2-space indent, UTF-8, LF, trailing newline."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def diff_summary(committed: Any, built: dict[str, Any]) -> list[str]:
    """Short, human-readable list of what differs between the committed KB and the rebuilt one."""
    if not isinstance(committed, dict):
        return ["committed KB is not a JSON object"]
    lines = []
    if committed.get("schema_version") != built["schema_version"]:
        lines.append(f"schema_version: committed {committed.get('schema_version')!r}, built {built['schema_version']!r}")
    for section in ("genes", "loci", "assemblies"):
        old, new = committed.get(section) or {}, built.get(section) or {}
        for key in sorted(set(old) - set(new)):
            lines.append(f"{section}: {key} only in the committed file")
        for key in sorted(set(new) - set(old)):
            lines.append(f"{section}: {key} missing from the committed file")
        for key in sorted(set(old) & set(new)):
            if old[key] != new[key]:
                fields = sorted(f for f in set(old[key]) | set(new[key]) if old[key].get(f) != new[key].get(f))
                lines.append(f"{section}: {key} differs in {', '.join(fields)}")
    old_manifest = committed.get("manifest") or {}
    for key in sorted(set(old_manifest) | set(built["manifest"])):
        if old_manifest.get(key) != built["manifest"].get(key):
            lines.append(f"manifest: {key} differs")
    return lines


# =============================================================================
# CLI (the only I/O)
# =============================================================================
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build web/src/knowledge-base.json from the curation file")
    parser.add_argument("--verify-only", action="store_true",
                        help="rebuild in memory and compare with the KB file; write nothing")
    parser.add_argument("--kb-path", type=Path, default=DEFAULT_KB_PATH, help="KB JSON file to write or compare")
    parser.add_argument("--curation-path", type=Path, default=DEFAULT_CURATION_PATH, help="curation source file")
    parser.add_argument("--upstream-path", type=Path, default=DEFAULT_UPSTREAM_ROOT, help="pinned upstream payload directory")
    args = parser.parse_args(argv)

    try:
        curation = load_curation(args.curation_path)
    except (OSError, ValueError) as exc:
        print(f"cannot read curation file {args.curation_path}: {exc}")
        return 1
    payload, errors = build_kb(curation, args.upstream_path)
    print(f"QC errors: {len(errors)}")
    for error in errors:
        print(f"  QC ERROR: {error}")
    if errors:
        return 1

    manifest = payload["manifest"]
    print(f"Release: {manifest['release']}  loci: {manifest['locus_count']}  genes: {manifest['gene_count']}")
    print(f"sha256: {manifest['sha256']}")
    rendered = render_kb(payload)

    if args.verify_only:
        if not args.kb_path.is_file():
            print(f"KB file not found: {args.kb_path}")
            return 1
        committed_text = args.kb_path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        if committed_text == rendered:
            print("KB up to date")
            return 0
        print(f"KB differs from the rebuild: {args.kb_path}")
        try:
            lines = diff_summary(json.loads(committed_text), payload)
        except ValueError as exc:
            lines = [f"committed KB is not valid JSON: {exc}"]
        for line in lines[:40] or ["content is equal but the serialization differs"]:
            print(f"  {line}")
        if len(lines) > 40:
            print(f"  ... and {len(lines) - 40} more")
        return 1

    args.kb_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.kb_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print(f"Wrote {args.kb_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
