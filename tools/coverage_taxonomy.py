"""
GenomePulse coverage taxonomy and evidence rules
================================================
The KB describes loci and what each alt-allele count means (contract C2). Whatever
depends on one person's sample is computed at analysis time and never stored in the KB.
This module holds the pure rules shared by the build and the desktop tools:

- `derive_evidence_tier` / `derive_evidence_sufficiency`: the KB build uses them to turn a
  locus's ClinVar review into an evidence tier (contract C2).
- `derive_coverage_state`: per-sample coverage state (contract C4). The desktop tools use
  it at analysis time. It is never called by the KB build.

Cardinal Principle:
"Absence of a finding must never imply absence of genetic risk."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional


# =============================================================================
# 1. COVERAGE STATES (computed per sample at analysis time, contract C4)
# =============================================================================

class CoverageState(str, Enum):
    """Five mutually exclusive per-sample coverage states."""
    SUPPORTED_AND_OBSERVED = "supported_and_observed"      # alt count > 0 at a curated locus
    SUPPORTED_NOT_OBSERVED = "supported_not_observed"      # alt count == 0 at a curated locus
    NOT_TESTED_BY_ARRAY = "not_tested_by_array"            # not assayed, no-call, or absent from a VCF
    OUTSIDE_COVERAGE = "outside_coverage"                  # marker present in the file but not curated
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"        # unresolvable genotype or insufficient locus evidence


VALID_COVERAGE_STATES: Final[set[str]] = {s.value for s in CoverageState}

VCF_ABSENT_REASON: Final[str] = "absent from VCF (variants-only VCFs omit reference calls)"
NOT_INTERPRETABLE_REASON: Final[str] = "genotype not interpretable"
INSUFFICIENT_LOCUS_REASON: Final[str] = "locus evidence is insufficient"


class EvidenceSufficiency(str, Enum):
    """Whether a locus's clinical evidence supports an assertion (derived from the tier)."""
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class CoverageEvaluation:
    """Result of `derive_coverage_state`."""
    state: CoverageState
    reason: Optional[str]
    variant_present: Optional[bool]  # None when no interpretable genotype exists


def derive_coverage_state(
    evidence_sufficiency: EvidenceSufficiency,
    *,
    curated: bool = True,
    assayed: bool = True,
    resolvable: bool = True,
    alt_count: Optional[int] = None,
    assay: str = "array",
) -> CoverageEvaluation:
    """Contract C4. Rules are applied in this order:

    1. not curated -> outside_coverage
    2. not assayed or no-call -> not_tested_by_array (a VCF records why it is absent)
    3. unresolvable genotype -> insufficient_evidence, "genotype not interpretable"
    4. locus evidence insufficient -> insufficient_evidence (variant presence still reported)
    5. alt count > 0 -> supported_and_observed; alt count == 0 -> supported_not_observed

    `variant_present` is True exactly when alt_count > 0 (AGENTS.md 4.2), whatever the state.
    """
    if not curated:
        return CoverageEvaluation(CoverageState.OUTSIDE_COVERAGE, None, None)
    if not assayed:
        reason = VCF_ABSENT_REASON if assay == "vcf" else "not assayed or no-call on this array"
        return CoverageEvaluation(CoverageState.NOT_TESTED_BY_ARRAY, reason, None)
    if not resolvable:
        return CoverageEvaluation(CoverageState.INSUFFICIENT_EVIDENCE, NOT_INTERPRETABLE_REASON, None)
    if alt_count not in (0, 1, 2):
        raise ValueError(f"alt_count must be 0, 1 or 2 for a resolvable genotype, got {alt_count!r}")
    present = alt_count > 0
    if evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT:
        return CoverageEvaluation(CoverageState.INSUFFICIENT_EVIDENCE, INSUFFICIENT_LOCUS_REASON, present)
    state = CoverageState.SUPPORTED_AND_OBSERVED if present else CoverageState.SUPPORTED_NOT_OBSERVED
    return CoverageEvaluation(state, None, present)


# =============================================================================
# 2. EVIDENCE TIERS
# =============================================================================
class EvidenceTier(str, Enum):
    """Conservative 4-tier evidence rating derived from the ClinVar review."""
    TIER_A = "Tier A"  # practice guideline or expert panel (3-4 stars)
    TIER_B = "Tier B"  # multiple submitters, no conflicts (2 stars)
    TIER_C = "Tier C"  # single submitter (1 star)
    TIER_D = "Tier D"  # no assertion criteria, conflicting, or no ClinVar record


def derive_evidence_tier(stars: Optional[int], conflicting: bool = False) -> EvidenceTier:
    """Tier from ClinVar stars: 3-4 -> A, 2 -> B, 1 -> C; 0, conflicting or missing -> D."""
    if stars is not None and stars not in (0, 1, 2, 3, 4):
        raise ValueError(f"ClinVar stars must be 0..4 or None, got {stars!r}")
    if conflicting or stars is None or stars == 0:
        return EvidenceTier.TIER_D
    if stars >= 3:
        return EvidenceTier.TIER_A
    return EvidenceTier.TIER_B if stars == 2 else EvidenceTier.TIER_C


def derive_tier_from_cpic_level(level: Optional[str]) -> EvidenceTier:
    """Tier for a pharmacogenomic locus from its CPIC level: A -> A, B -> B, C or D -> C, no guideline -> D."""
    if level is None:
        return EvidenceTier.TIER_D
    try:
        return {"A": EvidenceTier.TIER_A, "B": EvidenceTier.TIER_B,
                "C": EvidenceTier.TIER_C, "D": EvidenceTier.TIER_C}[level]
    except KeyError:
        raise ValueError(f"CPIC level must be A, B, C, D or None, got {level!r}") from None


def derive_evidence_sufficiency(tier: EvidenceTier) -> EvidenceSufficiency:
    """Tier A and B are sufficient; C and D are insufficient."""
    if tier in (EvidenceTier.TIER_A, EvidenceTier.TIER_B):
        return EvidenceSufficiency.SUFFICIENT
    return EvidenceSufficiency.INSUFFICIENT


# =============================================================================
# 3. CURATION MODES
# =============================================================================
class CurationMode(str, Enum):
    MACHINE_IMPORTED = "machine_imported"
    DERIVED = "derived"
    MANUALLY_CURATED = "manually_curated"


# =============================================================================
# 4. CORE SCIENTIFIC GUARDRAILS & CAVEATS
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
