"""
GenomePulse Coverage Taxonomy & Interpretation Scope
====================================================
Defines the formal coverage taxonomy and refactors variant evaluation into
four orthogonal scientific dimensions:

1. Assay Coverage (AssayCoverage / AssayInterrogation):
   - ASSAYED_CALLED: Probed and validly called on the microarray
   - NO_CALL: Interrogated on the array but uncallable ('--', '00', 'NN')
   - UNPROBED: Omitted from the microarray manifest (array gap)

2. Curation Scope (CurationScope):
   - IN_SCOPE: Within GenomePulse's curated clinical variome panel
   - OUT_OF_SCOPE: Array marker outside curated variome

3. Evidence Sufficiency (EvidenceSufficiency):
   - SUFFICIENT: Guideline / multi-submitter consensus without conflict (Tier A/B)
   - INSUFFICIENT: Conflicting classifications, weak single-submitter, or disputed (Tier C/D)
   - UNASSESSED: Outside curated catalog; clinical validity not evaluated

4. Sample Observation (SampleObservation):
   - VARIANT_PRESENT: Non-reference / risk / carrier / actionable allele observed
   - WILD_TYPE: Homozygous reference / benign baseline genotype observed
   - CALL_UNAVAILABLE: Unprobed or uncallable genotype

And deterministically derives user-facing CoverageState and human-readable labels:
- SUPPORTED_AND_OBSERVED: Curated locus, sufficient evidence, risk/carrier allele detected
- SUPPORTED_NOT_OBSERVED: Curated locus, sufficient evidence, homozygous reference detected
- NOT_TESTED_BY_ARRAY: Curated locus omitted from chip or uncallable
- OUTSIDE_COVERAGE: Marker assayed on array but uncurated
- INSUFFICIENT_EVIDENCE: Curated locus with conflicting, weak, or disputed clinical evidence

Cardinal Principle:
"Absence of a finding must never imply absence of genetic risk."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional


# =============================================================================
# 1. FOUR ORTHOGONAL EVALUATION DIMENSIONS
# =============================================================================

class AssayCoverage(str, Enum):
    """
    Dimension 1: Microarray Interrogation & Callability Status.
    Answers: Did this assay physically interrogate and successfully call this locus?
    """
    ASSAYED_CALLED = "assayed_called"    # Assayed with valid genotype call ('AA', 'AG', 'CT', etc.)
    NO_CALL = "no_call"                  # Interrogated on chip but uncallable ('--', '00', 'NN')
    UNPROBED = "unprobed"                # Omitted from this microarray platform manifest


class CurationScope(str, Enum):
    """
    Dimension 2: GenomePulse Curation & Support Scope.
    Answers: Is this locus curated within GenomePulse's clinical variome panel?
    """
    IN_SCOPE = "in_scope"                # Formally curated in GenomePulse high-confidence catalog
    OUT_OF_SCOPE = "out_of_scope"        # Marker assayed on array but outside curated catalog


class EvidenceSufficiency(str, Enum):
    """
    Dimension 3: Clinical & Empirical Evidence Sufficiency.
    Answers: Does the scientific evidence meet the standard for clinical/actionable assertion?
    """
    SUFFICIENT = "sufficient"            # Guideline, expert consensus, or robust multi-submitter (Tier A/B)
    INSUFFICIENT = "insufficient"        # Conflicting classifications, weak single-submitter, or disputed (Tier C/D)
    UNASSESSED = "unassessed"            # Outside curated catalog; clinical validity unassessed


class SampleObservation(str, Enum):
    """
    Dimension 4: Empirical Sample Finding.
    Answers: What did the patient's individual DNA exhibit at this locus?
    """
    VARIANT_PRESENT = "variant_present"    # Non-reference / risk / carrier / actionable genotype observed
    WILD_TYPE = "wild_type"                # Homozygous reference / baseline normal genotype observed
    CALL_UNAVAILABLE = "call_unavailable"  # No genotype call available (unprobed or no-call)


# =============================================================================
# 2. FIVE MUTUALLY EXCLUSIVE USER-FACING COVERAGE STATES (DERIVED)
# =============================================================================

class CoverageState(str, Enum):
    """
    Derived user-facing coverage states.
    Maintained for deterministic reporting and backward compatibility.
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


@dataclass(frozen=True)
class LocusCoverageEvaluation:
    """
    Complete orthogonal evaluation record for a locus in a sample.
    Separates assay coverage, curation scope, evidence sufficiency, and sample observation.
    """
    assay_coverage: AssayCoverage
    curation_scope: CurationScope
    evidence_sufficiency: EvidenceSufficiency
    sample_observation: SampleObservation
    derived_state: CoverageState
    user_label: str
    explanation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "assay_coverage": self.assay_coverage.value,
            "curation_scope": self.curation_scope.value,
            "evidence_sufficiency": self.evidence_sufficiency.value,
            "sample_observation": self.sample_observation.value,
            "derived_state": self.derived_state.value,
            "user_label": self.user_label,
            "explanation": self.explanation
        }


def derive_coverage_evaluation(
    assay: AssayCoverage,
    scope: CurationScope,
    evidence: EvidenceSufficiency,
    observation: SampleObservation
) -> LocusCoverageEvaluation:
    """
    Deterministically derives user-facing CoverageState and label from the 4 orthogonal dimensions:
    - Out of scope markers -> OUTSIDE_COVERAGE
    - Unprobed or no-call markers -> NOT_TESTED_BY_ARRAY
    - Insufficient or conflicting evidence -> INSUFFICIENT_EVIDENCE
    - Sufficient evidence + variant observed -> SUPPORTED_AND_OBSERVED
    - Sufficient evidence + wild-type observed -> SUPPORTED_NOT_OBSERVED
    """
    if scope == CurationScope.OUT_OF_SCOPE:
        state = CoverageState.OUTSIDE_COVERAGE
        label = "Outside Scope"
        expl = "Marker was genotyped on the array but is outside GenomePulse's curated variome catalog."
    elif assay in (AssayCoverage.UNPROBED, AssayCoverage.NO_CALL):
        state = CoverageState.NOT_TESTED_BY_ARRAY
        label = "Array Gap" if assay == AssayCoverage.UNPROBED else "No-Call"
        expl = (
            "Curated locus was omitted from this microarray design/manifest. Absence of a finding does NOT imply absence of risk."
            if assay == AssayCoverage.UNPROBED else
            "Curated locus was interrogated on the array but failed QC and produced an uncallable genotype ('--')."
        )
    elif evidence == EvidenceSufficiency.INSUFFICIENT:
        state = CoverageState.INSUFFICIENT_EVIDENCE
        label = "Conflicting Evidence"
        expl = (
            "Locus exhibits conflicting clinical interpretations or disputed utility (e.g. MTHFR). Variant allele detected."
            if observation == SampleObservation.VARIANT_PRESENT else
            "Locus exhibits conflicting clinical interpretations; wild-type baseline observed."
        )
    elif observation == SampleObservation.VARIANT_PRESENT:
        state = CoverageState.SUPPORTED_AND_OBSERVED
        label = "Supported & Observed"
        expl = "Curated locus with sufficient clinical consensus; variant/risk/actionable allele detected in sample."
    elif observation == SampleObservation.WILD_TYPE:
        state = CoverageState.SUPPORTED_NOT_OBSERVED
        label = "Tested Wild-Type"
        expl = "Curated locus with sufficient clinical consensus; homozygous reference/wild-type detected in sample."
    else:
        state = CoverageState.NOT_TESTED_BY_ARRAY
        label = "Call Unavailable"
        expl = "Genotype call unavailable."

    return LocusCoverageEvaluation(
        assay_coverage=assay,
        curation_scope=scope,
        evidence_sufficiency=evidence,
        sample_observation=observation,
        derived_state=state,
        user_label=label,
        explanation=expl
    )


# =============================================================================
# 3. SUPPORTED INTERPRETATION CATEGORIES
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
# 4. EVIDENCE TIERS
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
# 5. CURATION MODES
# =============================================================================
class CurationMode(str, Enum):
    MACHINE_IMPORTED = "machine_imported"
    DERIVED = "derived"
    MANUALLY_CURATED = "manually_curated"


# =============================================================================
# 6. CORE SCIENTIFIC GUARDRAILS & CAVEATS
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
