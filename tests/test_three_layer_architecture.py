"""
Unit Tests for 3-Layer Knowledge Separation Architecture (Item 3)
=================================================================
Validates:
1. Complete separation between:
   - IdentityLayer: physical coordinates, alleles, build mapping, HGVS
   - EvidenceLayer: ClinVar submissions, frequencies, transcripts, CPIC evidence, tiers
   - InterpretationLayer: user-facing clinical guidance, magnitude, caveats, refusals
2. Curated interpretation semantics are not silently overwritten by evidence changes.
3. Relational SQLite store (canonical_variome.db) schema and tables.
4. JSON distribution artifact structure and integrity.
"""

import os
import sqlite3
import json
import unittest
from tools.variome_models import (
    IdentityLayer,
    EvidenceLayer,
    InterpretationLayer,
    GenotypeInterpretation,
    CanonicalLocusRecord,
)
from tools.build_canonical_kb import COMPILED_LOCI, build_sqlite_variome_db


class TestThreeLayerArchitecture(unittest.TestCase):

    def test_locus_records_have_clean_three_layers(self):
        """Every compiled locus must have distinct Identity, Evidence, and Interpretation layers."""
        for locus in COMPILED_LOCI:
            self.assertIsInstance(locus.identity, IdentityLayer)
            self.assertIsInstance(locus.evidence, EvidenceLayer)
            self.assertIsInstance(locus.interpretation, InterpretationLayer)

            # Identity layer checks
            self.assertTrue(locus.identity.rsid.startswith("rs"))
            self.assertGreater(locus.identity.pos_grch37, 0)
            self.assertGreater(locus.identity.pos_grch38, 0)
            self.assertTrue(len(locus.identity.ref) >= 1)
            self.assertTrue(len(locus.identity.alt) >= 1)

            # Evidence layer checks
            self.assertTrue(0 <= locus.evidence.clinvar_stars <= 4)
            self.assertTrue(0.0 <= locus.evidence.gnomad_af <= 1.0)
            self.assertIn(locus.evidence.evidence_tier.value, ["Tier A", "Tier B", "Tier C", "Tier D"])

            # Interpretation layer checks
            self.assertTrue(len(locus.interpretation.supported_genotypes) >= 1)
            for gt, interp in locus.interpretation.supported_genotypes.items():
                self.assertIsInstance(interp, GenotypeInterpretation)
                self.assertTrue(0.0 <= interp.magnitude <= 10.0)
                self.assertIn(interp.repute, ["Good", "Bad", "Neutral"])
                self.assertTrue(len(interp.phenotype) > 0)

    def test_interpretation_isolation_from_evidence_updates(self):
        """Modifying evidence properties must not alter curated interpretation semantics."""
        import copy
        locus = copy.deepcopy(COMPILED_LOCI[0])
        first_gt = list(locus.interpretation.supported_genotypes.keys())[0]
        original_guidance = locus.interpretation.supported_genotypes[first_gt].user_guidance

        # Simulate upstream evidence update: ClinVar stars or frequency changes
        locus.evidence.clinvar_stars = 4
        locus.evidence.gnomad_af = 0.005

        current_guidance = locus.interpretation.supported_genotypes[first_gt].user_guidance
        self.assertEqual(original_guidance, current_guidance, "Interpretation guidance was altered by evidence update")

    def test_sqlite_canonical_variome_database_structure(self):
        """Verify the SQLite relational schema has all required tables and correct structure."""
        test_db_path = "test_variome.db"
        if os.path.exists(test_db_path):
            os.remove(test_db_path)

        try:
            build_sqlite_variome_db(COMPILED_LOCI, test_db_path)
            self.assertTrue(os.path.exists(test_db_path))

            conn = sqlite3.connect(test_db_path)
            cursor = conn.cursor()

            # Verify tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            expected_tables = {
                "identity_layer",
                "evidence_layer",
                "interpretation_layer",
                "genotype_interpretations",
                "provenance_lineage"
            }
            self.assertTrue(expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}")

            # Verify row counts match compiled loci
            cursor.execute("SELECT COUNT(*) FROM identity_layer")
            id_count = cursor.fetchone()[0]
            self.assertEqual(id_count, len(COMPILED_LOCI))

            cursor.execute("SELECT COUNT(*) FROM evidence_layer")
            ev_count = cursor.fetchone()[0]
            self.assertEqual(ev_count, len(COMPILED_LOCI))

            cursor.execute("SELECT COUNT(*) FROM interpretation_layer")
            int_count = cursor.fetchone()[0]
            self.assertEqual(int_count, len(COMPILED_LOCI))

            cursor.execute("SELECT COUNT(*) FROM genotype_interpretations")
            gt_count = cursor.fetchone()[0]
            self.assertGreater(gt_count, len(COMPILED_LOCI))

            cursor.execute("SELECT COUNT(*) FROM provenance_lineage")
            prov_count = cursor.fetchone()[0]
            self.assertGreater(prov_count, 0)

            conn.close()
        finally:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)

    def test_browser_json_artifact_schema_and_contents(self):
        """Verify the web/src/knowledge-base.json file follows the 3-layer architecture."""
        json_path = os.path.join("web", "src", "knowledge-base.json")
        self.assertTrue(os.path.exists(json_path), "JSON artifact must exist")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("manifest", data)
        self.assertIn("cardinal_guardrail", data["manifest"]["coverage_taxonomy"])
        self.assertEqual(data["manifest"]["schema_version"], "3.0.0")
        self.assertIn("variants", data)
        self.assertEqual(len(data["variants"]), len(COMPILED_LOCI))

        # Check first locus structure in JSON
        first_rsid = list(data["variants"].keys())[0]
        first_locus = data["variants"][first_rsid]
        self.assertIn("identity", first_locus)
        self.assertIn("evidence", first_locus)
        self.assertIn("interpretation", first_locus)
        self.assertIn("provenance", first_locus)


if __name__ == "__main__":
    unittest.main()
