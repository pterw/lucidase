"""
Unit Tests for GenomePulse Formal Coverage Taxonomy (Item 1)
============================================================
Validates:
1. 5 mutually exclusive coverage states:
   - supported_and_observed
   - supported_not_observed
   - not_tested_by_array
   - outside_coverage
   - insufficient_evidence
2. Cardinal scope guardrail enforcement:
   "Absence of a finding must never imply absence of genetic risk"
3. Incomplete star-allele refusal requirement on all PGx loci.
4. ACMG single-locus test caveats on ACMG SF loci.
5. Invariant checking in build_canonical_kb.py fails non-zero on violations.
"""

import unittest
from tools.coverage_taxonomy import (
    CoverageState,
    EvidenceTier,
    InterpretationCategory,
    CurationMode,
    ABSENCE_OF_FINDING_GUARDRAIL,
    INCOMPLETE_STAR_ALLELE_REFUSAL,
    ACMG_SINGLE_LOCUS_CAVEAT,
    VALID_COVERAGE_STATES
)
from tools.variome_models import CanonicalLocusRecord
from tools.build_canonical_kb import COMPILED_LOCI, QCValidator


class TestCoverageTaxonomy(unittest.TestCase):

    def test_five_coverage_states_defined_and_distinct(self):
        """Test that all 5 coverage states are mutually exclusive and defined."""
        states = [
            CoverageState.SUPPORTED_AND_OBSERVED.value,
            CoverageState.SUPPORTED_NOT_OBSERVED.value,
            CoverageState.NOT_TESTED_BY_ARRAY.value,
            CoverageState.OUTSIDE_COVERAGE.value,
            CoverageState.INSUFFICIENT_EVIDENCE.value,
        ]
        self.assertEqual(len(states), 5)
        self.assertEqual(len(set(states)), 5, "Coverage states must be mutually exclusive")
        self.assertEqual(VALID_COVERAGE_STATES, set(states))

    def test_cardinal_scope_guardrail_verbiage(self):
        """Cardinal guardrail must explicitly state absence of finding does not imply absence of risk."""
        self.assertIn("absence of a finding does not imply absence of genetic risk", ABSENCE_OF_FINDING_GUARDRAIL.lower())
        self.assertIn("targeted single-nucleotide polymorphisms", ABSENCE_OF_FINDING_GUARDRAIL.lower())

    def test_pgx_incomplete_star_allele_refusal(self):
        """All pharmacogenomic loci must include the formal star-allele refusal notice."""
        pgx_count = 0
        for locus in COMPILED_LOCI:
            if locus.interpretation.category == InterpretationCategory.PHARMACOGENOMICS_CPIC:
                pgx_count += 1
                self.assertTrue(
                    any(INCOMPLETE_STAR_ALLELE_REFUSAL in notice for notice in locus.interpretation.refusal_notices),
                    f"PGx locus {locus.rsid} missing incomplete star-allele refusal notice"
                )
        self.assertGreaterEqual(pgx_count, 3, "Expected at least 3 PGx loci (CYP2C19, SLCO1B1, DPYD)")

    def test_acmg_single_locus_caveat(self):
        """All ACMG Secondary Findings loci must include single-locus testing caveat."""
        acmg_count = 0
        for locus in COMPILED_LOCI:
            if locus.interpretation.acmg_sf_actionable:
                acmg_count += 1
                self.assertTrue(
                    any(ACMG_SINGLE_LOCUS_CAVEAT in caveat for caveat in locus.interpretation.caveats),
                    f"ACMG locus {locus.rsid} missing single-locus caveat"
                )
        self.assertGreaterEqual(acmg_count, 2, "Expected at least 2 ACMG loci (HFE C282Y, H63D)")

    def test_insufficient_evidence_loci_flagged(self):
        """MTHFR C677T must be designated Tier C with conflicting clinical evidence."""
        mthfr = next((l for l in COMPILED_LOCI if l.rsid == "rs1801133"), None)
        self.assertIsNotNone(mthfr)
        self.assertEqual(mthfr.evidence.evidence_tier, EvidenceTier.TIER_C)
        self.assertIn("Conflicting", mthfr.evidence.clinvar_significance)
        self.assertTrue(any("ACOG" in c or "ACMG" in c for c in mthfr.interpretation.caveats))

    def test_qc_validator_catches_missing_pgx_refusal(self):
        """Validator must report error if PGx locus lacks star-allele refusal."""
        import copy
        bad_loci = copy.deepcopy(COMPILED_LOCI)
        for l in bad_loci:
            if l.interpretation.category == InterpretationCategory.PHARMACOGENOMICS_CPIC:
                l.interpretation.refusal_notices = []
                break
        validator = QCValidator(bad_loci)
        errors = validator.validate_all()
        self.assertTrue(any("INCOMPLETE_STAR_ALLELE_REFUSAL" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
