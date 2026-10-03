"""
Unit Tests for Upstream Source Ingestion Architecture & Provenance (Item 2)
===========================================================================
Validates:
1. Pinned upstream data ingestion for ClinVar, dbSNP, Ensembl, gnomAD, CPIC, AlphaFold, HPA, and ENCODE.
2. Canonical FieldProvenance schema and licensing compliance.
3. Fail-closed scientific invariants:
   - Missing review/stars defaults to Tier D (never Tier A).
   - Missing gnomAD AF or constraint returns None (never 0.0).
   - Missing AlphaFold pLDDT returns None (never defaults to 80.0 or 0.0).
4. Evidence tier derivation transparent logic.
"""

from pathlib import Path
import unittest
from tools.source_adapters import (
    ClinVarSourceAdapter,
    DbSnpSourceAdapter,
    EnsemblSourceAdapter,
    GnomadSourceAdapter,
    CpicSourceAdapter,
    AlphaFoldSourceAdapter,
    HpaSourceAdapter,
    EncodeSourceAdapter,
    derive_evidence_tier,
)
from tools.variome_models import UPSTREAM_LICENSES, FieldProvenance
from tools.coverage_taxonomy import EvidenceTier, CurationMode

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tools" / "fixtures" / "upstream"


class TestSourceAdaptersAndProvenance(unittest.TestCase):

    def test_upstream_license_registry_completeness(self):
        """All upstream sources must have documented licenses and distribution terms."""
        expected_sources = [
            "ClinVar", "dbSNP", "Ensembl", "gnomAD", "CPIC",
            "AlphaFold DB", "Human Protein Atlas", "ENCODE"
        ]
        for src in expected_sources:
            self.assertIn(src, UPSTREAM_LICENSES, f"Source {src} missing from UPSTREAM_LICENSES")
            lic = UPSTREAM_LICENSES[src]
            self.assertIn("license", lic)
            self.assertIn("redistribution", lic)
            self.assertIn("commercial_use", lic)
            self.assertIn("citation", lic)

    def test_clinvar_adapter_ingestion_from_pinned_fixture(self):
        """ClinVar adapter ingests real pinned VCV fixture and derives stars/tier."""
        adapter = ClinVarSourceAdapter()
        fixture_path = FIXTURES_DIR / "clinvar" / "VCV000017864.json"
        res = adapter.ingest_from_file(fixture_path, rsid="rs429358")

        self.assertEqual(res["variation_id"], "17864")
        self.assertEqual(res["vcv_accession"], "VCV000017864.5")
        self.assertEqual(res["review_stars"], 3)
        self.assertEqual(res["review_status"], "reviewed by expert panel")
        self.assertEqual(res["clinical_significance"], "Risk factor")
        self.assertIn("Late-onset Alzheimer disease", res["phenotypes"])
        self.assertEqual(res["evidence_tier"], EvidenceTier.TIER_A)

        prov = res["provenance"]
        self.assertIsInstance(prov, FieldProvenance)
        self.assertEqual(prov.source, "NCBI ClinVar")
        self.assertEqual(prov.source_release, "Release 2024-06")
        self.assertEqual(prov.accession_id, "VCV000017864.5")
        self.assertIn("Public Domain", prov.license)

    def test_clinvar_adapter_fails_closed_on_missing_review(self):
        """Missing ClinVar review criteria must fail closed to Tier D."""
        adapter = ClinVarSourceAdapter()
        raw = {"variation_id": "99999"}
        res = adapter.ingest_record(raw, rsid="rsTest")
        self.assertEqual(res["review_stars"], 0)
        self.assertEqual(res["evidence_tier"], EvidenceTier.TIER_D)

    def test_dbsnp_adapter_ingestion_from_pinned_fixture(self):
        """dbSNP adapter ingests real dual GRCh37/GRCh38 coordinates and alleles."""
        adapter = DbSnpSourceAdapter()
        fixture_path = FIXTURES_DIR / "dbsnp" / "rs429358.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["rsid"], "rs429358")
        self.assertEqual(res["chrom"], "19")
        self.assertEqual(res["pos_grch37"], 45411941)
        self.assertEqual(res["pos_grch38"], 44908684)
        self.assertEqual(res["ref"], "T")
        self.assertEqual(res["alt"], "C")
        self.assertFalse(res["is_palindromic"])
        self.assertEqual(res["provenance"].source, "NCBI dbSNP")
        self.assertIn("Build 156", res["provenance"].source_release)

    def test_ensembl_adapter_ingestion_from_pinned_fixture(self):
        """Ensembl adapter extracts MANE Select transcript and AlphaMissense score."""
        adapter = EnsemblSourceAdapter()
        fixture_path = FIXTURES_DIR / "ensembl" / "vep_rs429358.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["rsid"], "rs429358")
        self.assertEqual(res["mane_transcript"], "ENST00000252486")
        self.assertEqual(res["hgvs_coding"], "ENST00000252486.9:c.388T>C")
        self.assertEqual(res["hgvs_protein"], "ENSP00000252486.4:p.Cys130Arg")
        self.assertEqual(res["alphamissense_class"], "likely_pathogenic")
        self.assertEqual(res["alphamissense_score"], 0.78)
        self.assertEqual(res["provenance"].source, "Ensembl VEP / MANE Select")

    def test_gnomad_adapter_ingestion_from_pinned_fixture(self):
        """gnomAD adapter extracts frequency and gene constraint scores."""
        adapter = GnomadSourceAdapter()
        fixture_path = FIXTURES_DIR / "gnomad" / "gnomad_19-44908684-T-C.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["variant_id"], "19-44908684-T-C")
        self.assertAlmostEqual(res["gnomad_af"], 0.145, places=3)
        self.assertEqual(res["gnomad_pli"], 0.0)
        self.assertEqual(res["gnomad_loeuf"], 1.12)
        self.assertEqual(res["provenance"].source, "gnomAD")
        self.assertEqual(res["provenance"].source_release, "v4.1.0")

    def test_gnomad_adapter_fails_closed_on_missing_values(self):
        """Missing gnomAD values must be None and not masquerade as 0.0."""
        adapter = GnomadSourceAdapter()
        raw = {"variantId": "1-12345-A-G"}
        res = adapter.ingest_record(raw)
        self.assertIsNone(res["gnomad_af"], "Missing AF must be None, not 0.0")
        self.assertIsNone(res["gnomad_pli"], "Missing pLI must be None, not 0.0")
        self.assertIsNone(res["gnomad_loeuf"], "Missing LOEUF must be None, not 0.0")

    def test_cpic_adapter_ingestion_from_pinned_fixture(self):
        """CPIC adapter ingests pharmacogenomic guideline recommendation."""
        adapter = CpicSourceAdapter()
        fixture_path = FIXTURES_DIR / "cpic" / "cpic_CYP2C19_clopidogrel.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["gene"], "CYP2C19")
        self.assertEqual(res["drug"], "clopidogrel")
        self.assertEqual(res["cpic_level"], "A")
        self.assertIn("Alternative antiplatelet", res["drug_recommendation"])
        self.assertEqual(res["provenance"].source, "CPIC Guidelines")

    def test_alphafold_adapter_ingestion_from_pinned_fixture(self):
        """AlphaFold DB adapter extracts global mean pLDDT and domains."""
        adapter = AlphaFoldSourceAdapter()
        fixture_path = FIXTURES_DIR / "alphafold" / "AF-P02649-F1-metadata.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["uniprot_accession"], "P02649")
        self.assertEqual(res["global_plddt"], 75.5)
        self.assertEqual(len(res["domains"]), 2)
        self.assertEqual(res["provenance"].source, "AlphaFold Protein Structure Database")

    def test_alphafold_adapter_fails_closed_on_missing_plddt(self):
        """Missing pLDDT must be None and not default to 80.0."""
        adapter = AlphaFoldSourceAdapter()
        raw = {"uniprotAccession": "P12345"}
        res = adapter.ingest_record(raw)
        self.assertIsNone(res["global_plddt"], "Missing pLDDT must be None, never 80.0")

    def test_hpa_adapter_ingestion_from_pinned_fixture(self):
        """Human Protein Atlas adapter ingests normal tissue proteomics."""
        adapter = HpaSourceAdapter()
        fixture_path = FIXTURES_DIR / "hpa" / "hpa_APOE.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["gene"], "APOE")
        self.assertEqual(res["tissues"]["liver"], "High")
        self.assertIn("Secreted", res["subcellular"])
        self.assertEqual(res["provenance"].source, "Human Protein Atlas")

    def test_encode_adapter_ingestion_from_pinned_fixture(self):
        """ENCODE SCREEN adapter ingests candidate cis-Regulatory Elements."""
        adapter = EncodeSourceAdapter()
        fixture_path = FIXTURES_DIR / "encode" / "encode_APOE_ccre.json"
        res = adapter.ingest_from_file(fixture_path)

        self.assertEqual(res["accession"], "EH38E1519412")
        self.assertEqual(res["ccre_type"], "Candidate Enhancer (dELS)")
        self.assertEqual(res["nearest_gene"], "APOE")
        self.assertEqual(res["provenance"].source, "ENCODE SCREEN")

    def test_derive_evidence_tier_logic(self):
        """Evidence tier mapping derives transparently from source review status and guidelines."""
        # Practice guideline -> Tier A
        tier_a1 = derive_evidence_tier(clinvar_review="practice_guideline", cpic_level=None)
        self.assertEqual(tier_a1, EvidenceTier.TIER_A)

        # CPIC Level A -> Tier A
        tier_a2 = derive_evidence_tier(clinvar_review="single_submitter", cpic_level="A")
        self.assertEqual(tier_a2, EvidenceTier.TIER_A)

        # Multiple submitters with no conflicts -> Tier B
        tier_b = derive_evidence_tier(
            clinvar_review="criteria_provided,_multiple_submitters,_no_conflicts",
            cpic_level=None
        )
        self.assertEqual(tier_b, EvidenceTier.TIER_B)

        # Conflicting interpretations -> Tier C
        tier_c = derive_evidence_tier(
            clinvar_review="conflicting_interpretations",
            cpic_level=None
        )
        self.assertEqual(tier_c, EvidenceTier.TIER_C)

        # Research / functional only / missing -> Tier D (fails closed)
        tier_d = derive_evidence_tier(
            clinvar_review="no_assertion_criteria_provided",
            cpic_level=None
        )
        self.assertEqual(tier_d, EvidenceTier.TIER_D)


if __name__ == "__main__":
    unittest.main()
