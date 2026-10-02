"""
GenomePulse Coverage Taxonomy & Interpretation Scope
====================================================
Defines the formal coverage taxonomy, 5 mutually exclusive coverage states,
evidence tiers, curation modes, and interpretation guardrails.

Cardinal Principle:
"Absence of a finding must never imply absence of genetic risk."
"""

from __future__ import annotations

from enum import Enum
from typing import Final

# =============================================================================
# 1. FIVE MUTUALLY EXCLUSIVE COVERAGE STATES
# =============================================================================
class CoverageState(str, Enum):
    """
    Every locus evaluated by GenomePulse resolves to exactly one coverage state.
    """
    # 1. Curated locus assayed by chip, non-reference / actionable / risk genotype observed
    SUPPORTED_AND_OBSERVED = "supported_and_observed"

    # 2. Curated locus assayed by chip, homozygous reference / benign wild-type observed
    SUPPORTED_NOT_OBSERVED = "supported_not_observed"

    # 3. Curated locus omitted by this specific microarray chip or uncallable (no-call '--')
    NOT_TESTED_BY_ARRAY = "not_tested_by_array"

    # 4. Marker assayed on array but outside GenomePulse's curated high-confidence variome
    OUTSIDE_COVERAGE = "outside_coverage"

    # 5. Locus present in catalog or input but marked by conflicting, weak, or unvalidated evidence
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


VALID_COVERAGE_STATES: Final[set[str]] = {s.value for s in CoverageState}


# =============================================================================
# 2. SUPPORTED INTERPRETATION CATEGORIES
# =============================================================================
class InterpretationCategory(str, Enum):
    """
    Formal categorization of curated variants within GenomePulse scope.
    """
    # High-confidence pathogenic / carrier variants with established clinical validity
    PATHOGENIC_CARRIER = "pathogenic_carrier"

    # ACMG Secondary Findings v3.2 loci where single-variant assay supports a meaningful statement
    ACMG_SF_LOCUS = "acmg_sf_locus"

    # Pharmacogenomics with CPIC Level A/B evidence, with explicit star-allele refusal
    PHARMACOGENOMICS_CPIC = "pharmacogenomics_cpic"

    # Common medically relevant risk alleles with replicated effect sizes (e.g. APOE-e4, F5 Leiden)
    MEDICALLY_RELEVANT_RISK = "medically_relevant_risk"

    # Selected ancestry-independent traits with scientific consensus (e.g. MCM6/LCT)
    SCIENTIFICALLY_DEFENSIBLE_TRAIT = "scientifically_defensible_trait"

    # Multi-locus epistatic or compound interactions (APOE diplotype, HFE C282Y/H63D)
    COMPOUND_MULTILOCUS = "compound_multilocus"


# =============================================================================
# 3. EVIDENCE TIERS
# =============================================================================
class EvidenceTier(str, Enum):
    """
    Conservative 4-tier evidence rating derived transparently from upstream consensus.
    """
    # Practice guideline or expert panel (ClinVar 3-4 stars, CPIC Level A)
    TIER_A = "Tier A"

    # Robust multi-submitter clinical consensus without conflicts (ClinVar 2 stars)
    TIER_B = "Tier B"

    # Limited, single-submitter, or conflicting clinical evidence (ClinVar 1 star, e.g. MTHFR)
    TIER_C = "Tier C"

    # Research / functional context only (GWAS exploratory, non-clinical)
    TIER_D = "Tier D"


# =============================================================================
# 4. CURATION MODES
# =============================================================================
class CurationMode(str, Enum):
    MACHINE_IMPORTED = "machine_imported"
    DERIVED = "derived"
    MANUALLY_CURATED = "manually_curated"


# =============================================================================
# 5. CORE SCIENTIFIC GUARDRAILS & CAVEATS
# =============================================================================
ABSENCE_OF_FINDING_GUARDRAIL: Final[str] = (
    "ABSENCE OF A FINDING DOES NOT IMPLY ABSENCE OF GENETIC RISK. "
    "GenomePulse analyzes only targeted single-nucleotide polymorphisms interrogated by consumer arrays. "
    "It does not perform full gene sequencing, does not analyze unprobed exonic or intronic regions, "
    "and cannot detect large copy-number variations (CNVs), balanced translocations, or structural repeats."
)

INCOMPLETE_STAR_ALLELE_REFUSAL: Final[str] = (
    "Incomplete star-allele coverage refusal: Interrogating an isolated SNP (e.g. *2) cannot rule out "
    "other active, decreased, or gain-of-function alleles (e.g. *3, *4, *17) not present on this array. "
    "A full metabolizer phenotype cannot and will not be inferred without complete haplotype sequencing."
)

ACMG_SINGLE_LOCUS_CAVEAT: Final[str] = (
    "ACMG Secondary Findings locus caveat: This finding represents interrogation of a single specific nucleotide "
    "locus only. It does NOT represent comprehensive clinical sequencing of the gene. A negative result at this "
    "single position does not rule out other pathogenic variants across the remainder of the gene."
)
