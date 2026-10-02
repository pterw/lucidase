"""
Canonical Variome Data Models: 3-Layer Knowledge Architecture
==============================================================
Enforces strict architectural separation between:
1. Identity Layer      - Genomic coordinates, REF/ALT, strand, palindromic status, HGVS.
2. Evidence Layer      - Upstream scientific evidence (ClinVar, gnomAD, Ensembl, AlphaFold, HPA, CPIC)
                         with full field-level provenance, curation mode, and license tracking.
3. Interpretation Layer- Curated clinical guidance, genotype assertions, caveats, and refusal notices.

Upstream evidence updates MUST NOT silently mutate or corrupt curated interpretation semantics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from tools.coverage_taxonomy import (
    CoverageState,
    CurationMode,
    EvidenceTier,
    InterpretationCategory,
)

class LicenseMeta(str):
    """String subclass supporting attribute and dict-like metadata access."""
    def __new__(cls, text: str, meta: Optional[dict[str, Any]] = None):
        obj = str.__new__(cls, text)
        obj._meta = meta or {}
        return obj

    def __getitem__(self, item: str) -> Any:
        if item == "license":
            return str(self)
        if item in self._meta:
            return self._meta[item]
        return str(self)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str) and item in self._meta:
            return True
        return super().__contains__(item)


def _make_license(name: str, redistribution: str, commercial: bool, citation: str) -> LicenseMeta:
    return LicenseMeta(name, {
        "license": name,
        "redistribution": redistribution,
        "commercial_use": commercial,
        "citation": citation
    })


# Standard upstream license definitions with full redistribution constraints
UPSTREAM_LICENSES: dict[str, LicenseMeta] = {
    "ncbi_clinvar": _make_license("Public Domain / Open Data (NCBI)", "Unrestricted open redistribution", True, "Landrum MJ, et al. ClinVar. Nucleic Acids Res. 2020"),
    "ncbi_dbsnp": _make_license("Public Domain (US Government / NLM)", "Unrestricted public domain", True, "Sherry ST, et al. dbSNP. Nucleic Acids Res. 2001"),
    "ensembl": _make_license("EMBL-EBI Open Terms of Use", "Freely available for academic and commercial use", True, "Martin FJ, et al. Ensembl 2023. Nucleic Acids Res. 2023"),
    "gnomad": _make_license("Open Access (Broad Institute, ODC-ODbL)", "Open Database License (ODbL) 1.0", True, "Chen S, et al. gnomAD v4. Nature 2024"),
    "cpic": _make_license("Creative Commons Attribution 4.0 International (CC-BY 4.0)", "Redistribution permitted with attribution", True, "Relling MV, et al. CPIC Guidelines. Clin Pharmacol Ther. 2020"),
    "hpa": _make_license("Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA 4.0)", "ShareAlike redistribution permitted with attribution", True, "Uhlén M, et al. Human Protein Atlas. Science 2015"),
    "alphafold_db": _make_license("Creative Commons Attribution 4.0 International (CC-BY 4.0)", "Redistribution permitted with attribution to DeepMind / EMBL-EBI", True, "Jumper J, et al. AlphaFold. Nature 2021"),
    "encode": _make_license("ENCODE Consortium Open Access Policy", "Unrestricted open access post-moratorium", True, "ENCODE Project Consortium. Nature 2020"),
    "acmg": _make_license("ACMG Educational & Clinical Practice Terms", "Educational and non-commercial clinical guidance reference", False, "Miller DT, et al. ACMG SF v3.2. Genet Med. 2023"),
}

# Aliases for friendly querying
UPSTREAM_LICENSES["ClinVar"] = UPSTREAM_LICENSES["ncbi_clinvar"]
UPSTREAM_LICENSES["dbSNP"] = UPSTREAM_LICENSES["ncbi_dbsnp"]
UPSTREAM_LICENSES["Ensembl"] = UPSTREAM_LICENSES["ensembl"]
UPSTREAM_LICENSES["gnomAD"] = UPSTREAM_LICENSES["gnomad"]
UPSTREAM_LICENSES["CPIC"] = UPSTREAM_LICENSES["cpic"]
UPSTREAM_LICENSES["Human Protein Atlas"] = UPSTREAM_LICENSES["hpa"]
UPSTREAM_LICENSES["AlphaFold DB"] = UPSTREAM_LICENSES["alphafold_db"]
UPSTREAM_LICENSES["ENCODE"] = UPSTREAM_LICENSES["encode"]
UPSTREAM_LICENSES["ACMG"] = UPSTREAM_LICENSES["acmg"]


@dataclass
class FieldProvenance:
    """Provenance audit record for an individual data field."""
    source: str
    source_release: str
    accession_id: str
    retrieval_timestamp: str
    transformation: str
    review_status: str
    curation_mode: CurationMode
    license: str


@dataclass
class IdentityLayer:
    """
    Layer 1: Identity
    Invariant genomic coordinates, alleles, and identifiers.
    """
    rsid: str
    aliases: list[str] = field(default_factory=list)
    chrom: str = ""
    pos_grch37: int = 0
    pos_grch38: int = 0
    ref: str = ""
    alt: str = ""
    is_palindromic: bool = False
    strand: str = "+"
    hgvs_genomic: str = ""
    hgvs_coding: str = ""
    hgvs_protein: str = ""


@dataclass
class EvidenceLayer:
    """
    Layer 2: Evidence
    Empirical and clinical observations imported from upstream repositories.
    """
    evidence_tier: EvidenceTier = EvidenceTier.TIER_A
    tier_rationale: str = ""
    clinvar_vcv: str = ""
    clinvar_stars: int = 0
    clinvar_status: str = ""
    clinvar_significance: str = ""
    clinvar_condition: str = ""
    clinvar_medgen: str = ""
    gnomad_af: float = 0.0
    gnomad_pli: float = 0.0
    gnomad_loeuf: Optional[float] = None
    mane_transcript: str = ""
    alphamissense_class: str = ""
    alphamissense_score: float = 0.0
    uniprot_id: str = ""
    alphafold_plddt: float = 0.0
    hpa_tissues: dict[str, str] = field(default_factory=dict)
    hpa_subcellular: list[str] = field(default_factory=list)
    encode_ccre: str = ""
    cpic_level: Optional[str] = None
    cpic_drug: Optional[str] = None
    literature_pmids: list[str] = field(default_factory=list)
    field_provenance: dict[str, FieldProvenance] = field(default_factory=dict)


@dataclass
class GenotypeInterpretation:
    """Interpretation assertion for a specific genotype call."""
    category: str                   # Pathogenic, Carrier, Pharmacogenomics, Risk Factor, Trait
    significance: str               # Short assertion label
    magnitude: float                # Clinical priority scale (0.0 to 10.0)
    repute: str                     # Good, Bad, Neutral
    coverage_state: CoverageState   # supported_and_observed vs supported_not_observed
    phenotype: str                  # Scientific phenotype description
    user_guidance: str              # Actionable, responsible patient guidance
    drug_response: Optional[str] = None
    is_carrier: bool = False


@dataclass
class InterpretationLayer:
    """
    Layer 3: Interpretation
    Curated clinical guidance and genotype assertions.
    """
    category: InterpretationCategory
    phenotype_summary: str
    acmg_sf_actionable: bool
    supported_genotypes: dict[str, GenotypeInterpretation]
    caveats: list[str] = field(default_factory=list)
    refusal_notices: list[str] = field(default_factory=list)
    multi_locus_dependencies: list[str] = field(default_factory=list)


@dataclass
class CanonicalLocusRecord:
    """Complete 3-layer canonical record for a single genetic locus."""
    rsid: str
    gene: str
    name: str
    identity: IdentityLayer
    evidence: EvidenceLayer
    interpretation: InterpretationLayer

    def to_dict(self) -> dict[str, Any]:
        """Serializes the complete record to a nested dictionary."""
        return asdict(self)
