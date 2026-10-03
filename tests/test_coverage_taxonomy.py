"""
Unit tests for the coverage taxonomy and the evidence rules (contracts C2 and C4).

The KB stores no per-sample fields. `derive_coverage_state` is the desktop's analysis-time
implementation of contract C4.
"""

import dataclasses
import unittest

from tools import coverage_taxonomy
from tools.build_canonical_kb import build_kb, load_curation
from tools.coverage_taxonomy import (
    ABSENCE_OF_FINDING_GUARDRAIL,
    ACMG_SINGLE_LOCUS_CAVEAT,
    INCOMPLETE_STAR_ALLELE_REFUSAL,
    NO_CALL_REASON,
    NOT_ASSAYED_REASON,
    NOT_INTERPRETABLE_REASON,
    VALID_COVERAGE_STATES,
    VCF_ABSENT_REASON,
    CoverageState,
    EvidenceSufficiency,
    EvidenceTier,
    derive_coverage_state,
)
from tools.variome_models import GenotypeInterpretation

SUFFICIENT = EvidenceSufficiency.SUFFICIENT
INSUFFICIENT = EvidenceSufficiency.INSUFFICIENT


class TestCoverageStates(unittest.TestCase):

    def test_five_coverage_states_defined_and_distinct(self):
        states = [s.value for s in CoverageState]
        self.assertEqual(len(states), 5)
        self.assertEqual(len(set(states)), 5, "Coverage states must be mutually exclusive")
        self.assertEqual(VALID_COVERAGE_STATES, set(states))

    def test_per_sample_evaluation_machinery_is_gone_from_the_kb_models(self):
        """CR-1: the old four-dimension evaluation (assay, scope, sufficiency, observation) is deleted."""
        for name in ("AssayCoverage", "CurationScope", "SampleObservation",
                     "LocusCoverageEvaluation", "derive_coverage_evaluation"):
            self.assertFalse(hasattr(coverage_taxonomy, name), name)
        fields = {f.name for f in dataclasses.fields(GenotypeInterpretation)}
        self.assertEqual(
            fields,
            {"category", "significance", "magnitude", "repute", "phenotype", "drug_response", "caveats"},
        )

    def test_not_curated_marker_is_outside_coverage(self):
        result = derive_coverage_state(SUFFICIENT, curated=False)
        self.assertEqual(result.state, CoverageState.OUTSIDE_COVERAGE)

    def test_not_assayed_or_no_call_is_not_tested_by_array(self):
        result = derive_coverage_state(SUFFICIENT, assayed=False)
        self.assertEqual(result.state, CoverageState.NOT_TESTED_BY_ARRAY)
        self.assertIsNone(result.variant_present)

    def test_array_reason_strings_are_the_wording_the_shared_vectors_fix(self):
        """The vectors (apoe.json) are the spec for both strings; the desktop imports them from here."""
        self.assertEqual(NOT_ASSAYED_REASON, "locus not assayed on this array")
        self.assertEqual(NO_CALL_REASON, "no-call at this locus")
        result = derive_coverage_state(SUFFICIENT, assayed=False, assay="array")
        self.assertEqual(result.reason, NOT_ASSAYED_REASON)

    def test_vcf_absence_records_why(self):
        result = derive_coverage_state(SUFFICIENT, assayed=False, assay="vcf")
        self.assertEqual(result.state, CoverageState.NOT_TESTED_BY_ARRAY)
        self.assertEqual(result.reason, VCF_ABSENT_REASON)
        self.assertEqual(VCF_ABSENT_REASON, "absent from VCF (variants-only VCFs omit reference calls)")

    def test_unresolvable_genotype_is_insufficient_evidence_even_with_sufficient_locus(self):
        result = derive_coverage_state(SUFFICIENT, resolvable=False)
        self.assertEqual(result.state, CoverageState.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.reason, NOT_INTERPRETABLE_REASON)
        self.assertEqual(NOT_INTERPRETABLE_REASON, "genotype not interpretable")
        self.assertIsNone(result.variant_present)

    def test_insufficient_locus_is_insufficient_evidence_but_still_reports_the_variant(self):
        carrier = derive_coverage_state(INSUFFICIENT, alt_count=1)
        self.assertEqual(carrier.state, CoverageState.INSUFFICIENT_EVIDENCE)
        self.assertTrue(carrier.variant_present)
        none = derive_coverage_state(INSUFFICIENT, alt_count=0)
        self.assertEqual(none.state, CoverageState.INSUFFICIENT_EVIDENCE)
        self.assertFalse(none.variant_present)

    def test_alt_count_decides_observed_versus_not_observed(self):
        for count in (1, 2):
            result = derive_coverage_state(SUFFICIENT, alt_count=count)
            self.assertEqual(result.state, CoverageState.SUPPORTED_AND_OBSERVED)
            self.assertTrue(result.variant_present)
        result = derive_coverage_state(SUFFICIENT, alt_count=0)
        self.assertEqual(result.state, CoverageState.SUPPORTED_NOT_OBSERVED)
        self.assertFalse(result.variant_present)

    def test_rule_order_not_tested_beats_unresolvable_beats_insufficient(self):
        self.assertEqual(
            derive_coverage_state(INSUFFICIENT, assayed=False, resolvable=False).state,
            CoverageState.NOT_TESTED_BY_ARRAY,
        )
        self.assertEqual(
            derive_coverage_state(INSUFFICIENT, resolvable=False).reason,
            NOT_INTERPRETABLE_REASON,
        )

    def test_a_resolvable_genotype_needs_an_alt_count(self):
        with self.assertRaises(ValueError):
            derive_coverage_state(SUFFICIENT)
        with self.assertRaises(ValueError):
            derive_coverage_state(SUFFICIENT, alt_count=3)


class TestGuardrailsAndKbRules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        payload, errors = build_kb(load_curation())
        assert errors == [], errors
        cls.kb = payload

    def test_cardinal_scope_guardrail_verbiage(self):
        self.assertIn("absence of a finding does not imply absence of genetic risk", ABSENCE_OF_FINDING_GUARDRAIL.lower())
        self.assertIn("targeted single-nucleotide polymorphisms", ABSENCE_OF_FINDING_GUARDRAIL.lower())
        self.assertEqual(self.kb["manifest"]["guardrail"], ABSENCE_OF_FINDING_GUARDRAIL)

    def test_pharmacogenomic_loci_carry_a_limitation(self):
        pgx = [r for r, l in self.kb["loci"].items()
               if self.kb["genes"][l["gene"]]["inheritance"]["model"] == "pharmacogenomic"]
        self.assertGreaterEqual(len(pgx), 4)  # CYP2C19, VKORC1, SLCO1B1, DPYD
        for rsid in pgx:
            self.assertTrue(self.kb["loci"][rsid]["limitation"], rsid)
        self.assertEqual(self.kb["loci"]["rs4244285"]["limitation"], INCOMPLETE_STAR_ALLELE_REFUSAL)

    def test_acmg_loci_carry_the_single_locus_caveat(self):
        acmg = [r for r, l in self.kb["loci"].items() if self.kb["genes"][l["gene"]]["acmg_sf"]]
        self.assertEqual(sorted(acmg), ["rs1799945", "rs1800562"])
        for rsid in acmg:
            self.assertEqual(self.kb["loci"][rsid]["limitation"], ACMG_SINGLE_LOCUS_CAVEAT)

    def test_conflicting_mendelian_locus_is_tier_d_and_insufficient(self):
        """H63D (HFE, Mendelian) carries ClinVar 'conflicting classifications' in the pinned capture."""
        locus = self.kb["loci"]["rs1799945"]
        self.assertEqual(locus["evidence_tier"], EvidenceTier.TIER_D.value)
        self.assertEqual(locus["evidence_sufficiency"], INSUFFICIENT.value)

    def test_apoe_tier_comes_from_the_curated_tier_not_the_conflicting_snv_record(self):
        """L7: ClinVar's conflicting record for the APOE SNV does not decide the risk-factor tier."""
        locus = self.kb["loci"]["rs429358"]
        self.assertIn("conflicting", locus["evidence"]["clinvar"]["review_status"])
        self.assertEqual(locus["evidence_tier"], EvidenceTier.TIER_A.value)
        self.assertEqual(locus["evidence_sufficiency"], "sufficient")


if __name__ == "__main__":
    unittest.main()
