"""
Tests for the identity / evidence / interpretation separation in KB schema v2 (contract C2).

1. Identity (coordinates, alleles), evidence (upstream-sourced values with provenance) and
   interpretations (what each alt-allele count means) are separate parts of a locus.
2. Curated interpretation semantics are not altered by an evidence update.
3. The KB is built in memory from the curation file. These tests never read the committed JSON.
"""

import copy
import unittest

from tools.build_canonical_kb import build_kb, load_curation
from tools.variome_models import GenotypeInterpretation

IDENTITY_KEYS = {"rsid", "gene", "chrom", "pos_grch37", "pos_grch38", "ref", "alt", "allele_codes", "role"}


class TestThreeLayerArchitecture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.curation = load_curation()
        cls.kb, errors = build_kb(copy.deepcopy(cls.curation))
        assert errors == [], errors

    def test_every_locus_keeps_the_three_layers_apart(self):
        for rsid, locus in self.kb["loci"].items():
            self.assertTrue(IDENTITY_KEYS <= set(locus), rsid)
            self.assertIsInstance(locus["evidence"], dict)
            self.assertIsInstance(locus["interpretations"], dict)
            self.assertTrue(rsid.startswith("rs"))
            self.assertGreater(locus["pos_grch37"], 0)
            self.assertGreater(locus["pos_grch38"], 0)
            self.assertGreaterEqual(len(locus["ref"]), 1)
            self.assertGreaterEqual(len(locus["alt"]), 1)
            # Evidence values are null when unknown, and every block carries provenance.
            for name in ("clinvar", "gnomad", "hpa"):
                self.assertIn("provenance", locus["evidence"][name], f"{rsid} {name}")
            # Interpretations are typed knowledge, nothing else.
            for count, interp in locus["interpretations"].items():
                self.assertEqual(interp, GenotypeInterpretation(**interp).to_dict(), f"{rsid} {count}")
                self.assertIn(interp["repute"], ["Good", "Bad", "Neutral"])
                self.assertTrue(interp["phenotype"])

    def test_interpretation_isolation_from_evidence_updates(self):
        """An upstream evidence update must not alter curated interpretation semantics."""
        before = copy.deepcopy(self.curation)
        after = copy.deepcopy(self.curation)
        rsid = "rs1800562"
        after["loci"][rsid]["evidence"]["clinvar"].update(
            review_status="practice guideline", stars=4, significance="Pathogenic"
        )
        after["loci"][rsid]["evidence"]["gnomad"]["af"] = 0.05
        kb_before, _ = build_kb(before)
        kb_after, errors = build_kb(after)
        self.assertEqual(errors, [])
        self.assertEqual(kb_before["loci"][rsid]["interpretations"], kb_after["loci"][rsid]["interpretations"])
        self.assertEqual(kb_before["loci"][rsid]["limitation"], kb_after["loci"][rsid]["limitation"])
        # The derived tier did change with the evidence, which is the point of keeping them apart.
        self.assertEqual(kb_before["loci"][rsid]["evidence_tier"], "Tier B")
        self.assertEqual(kb_after["loci"][rsid]["evidence_tier"], "Tier A")

    def test_locus_and_gene_counts_come_from_the_curation_file(self):
        self.assertEqual(self.kb["manifest"]["locus_count"], len(self.curation["loci"]))
        self.assertEqual(self.kb["manifest"]["gene_count"], len(self.curation["genes"]))

    def test_privacy_manifest_block(self):
        self.assertEqual(
            self.kb["manifest"]["privacy"],
            {"local_analysis": True, "genomic_uploads": False, "variant_identifiers_transmitted": False},
        )


if __name__ == "__main__":
    unittest.main()
