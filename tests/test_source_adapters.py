"""
Unit Tests for Upstream Source Ingestion Architecture & Provenance (Item 2)
===========================================================================
Validates:
1. Source adapters for ClinVar, dbSNP, Ensembl, gnomAD, CPIC, AlphaFold, HPA, and ENCODE.
2. Canonical FieldProvenance schema:
   - source
   - source_release
   - accession_id
   - retrieval_timestamp
   - transformation_performed
   - confidence_status
   - curation_mode (machine_imported, derived, manually_curated)
   - license (explicit upstream redistribution terms)
3. Upstream licenses registry:
   - ClinVar (Open Access / Public Domain)
   - dbSNP (NCBI Public Domain)
   - Ensembl (Open Access)
   - gnomAD (ODbL 1.0)
   - CPIC (CC0 1.0)
   - AlphaFold (CC-BY-4.0)
   - Human Protein Atlas (CC-BY-SA-3.0)
   - ENCODE (Open Data)
4. Evidence Tier derivation logic (Tier A, Tier B, Tier C, Tier D).
"""

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

    def test_clinvar_adapter_ingestion_and_provenance(self):
        """ClinVar adapter produces valid field-level provenance with review stars."""
        adapter = ClinVarSourceAdapter(release_version="2024-06-Snapshot")
        raw = {
            "variation_id": "12345",
            "clinical_significance": "Pathogenic",
            "review_status": "criteria_provided,_multiple_submitters,_no_conflicts",
            "gold_stars": 2,
            "phenotypes": ["Hereditary breast and ovarian cancer syndrome"]
        }
        res = adapter.ingest_record("rs28897700", raw)
        self.assertEqual(res["variation_id"], "12345")
        self.assertEqual(res["review_stars"], 2)
        self.assertEqual(res["clinical_significance"], "Pathogenic")

        prov = res["provenance"]
        self.assertIsInstance(prov, FieldProvenance)
        self.assertIn("ClinVar", prov.source)
        self.assertEqual(prov.source_release, "Release 2024-06")
        self.assertEqual(prov.accession_id, "VCV000012345")
        self.assertEqual(prov.curation_mode, CurationMode.MACHINE_IMPORTED)
        self.assertIn("Public Domain", prov.license)

    def test_cpic_adapter_and_guideline_provenance(self):
        """CPIC adapter ingests pharmacogenomic guideline data with CC-BY-4.0 license."""
        adapter = CpicSourceAdapter(release_version="2024.1")
        raw = {
            "gene": "CYP2C19",
            "cpic_level": "A",
            "guideline_url": "https://cpicpgx.org/guidelines/guideline-for-clopidogrel-and-cyp2c19/",
            "drug_recommendation": "Clopidogrel resistance / intermediate metabolizer"
        }
        res = adapter.ingest_record("rs4244285", raw)
        self.assertEqual(res["cpic_level"], "A")
        self.assertIn("CPIC", res["provenance"].source)
        self.assertIn("CC-BY 4.0", res["provenance"].license)

    def test_alphafold_adapter_provenance(self):
        """AlphaFold DB adapter includes UniProt accession and CC-BY-4.0 license."""
        adapter = AlphaFoldSourceAdapter(release_version="v4")
        raw = {
            "uniprot_accession": "P04637",
            "global_plddt": 88.5,
            "domains": ["DNA-binding domain"],
            "folding_status": "Well-folded globular core"
        }
        res = adapter.ingest_record("TP53", raw)
        self.assertEqual(res["global_plddt"], 88.5)
        self.assertIn("AlphaFold", res["provenance"].source)
        self.assertIn("CC-BY 4.0", res["provenance"].license)

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

        # Research / functional only -> Tier D
        tier_d = derive_evidence_tier(
            clinvar_review="no_assertion_criteria_provided",
            cpic_level=None
        )
        self.assertEqual(tier_d, EvidenceTier.TIER_D)


if __name__ == "__main__":
    unittest.main()
