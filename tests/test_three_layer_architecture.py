"""
Tests for the identity / evidence / interpretation separation in KB schema v2 (contract C2).

1. Identity (coordinates, alleles), evidence (upstream-sourced values with provenance) and
   interpretations (what each alt-allele count means) are separate parts of a locus.
2. Curated interpretation semantics are not altered by an evidence update.
3. The KB is built in memory from the curation file. These tests never read the committed JSON.
"""

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.build_canonical_kb import DEFAULT_UPSTREAM_ROOT as UPSTREAM_ROOT, build_kb, load_curation
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
        """An upstream evidence update must not alter curated interpretation semantics.

        The update is a changed ClinVar review status in a temp copy of the pinned payloads, with its
        meta sha256 re-pinned in the copy only. The committed fixtures are never touched.
        """
        rsid = "rs1800562"
        kb_before, errors = build_kb(copy.deepcopy(self.curation))
        self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "real"
            shutil.copytree(UPSTREAM_ROOT, root)
            body = root / "clinvar" / f"{rsid}.json"
            meta = root / "clinvar" / f"{rsid}.meta.json"
            data = body.read_bytes()
            old = b"criteria provided, multiple submitters, no conflicts"
            self.assertIn(old, data)
            data = data.replace(old, b"practice guideline")
            body.write_bytes(data)
            info = json.loads(meta.read_text(encoding="utf-8"))
            info["sha256_of_body"], info["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
            meta.write_text(json.dumps(info), encoding="utf-8")
            # The curated ClinVar fields must agree with the import (QC drift check), so the curator
            # re-transcribes the two evidence fields; interpretations and limitation are not touched.
            curation_after = copy.deepcopy(self.curation)
            curated_clinvar = curation_after["loci"][rsid]["evidence"]["clinvar"]
            curated_clinvar["review_status"], curated_clinvar["stars"] = "practice guideline", 4
            kb_after, errors = build_kb(curation_after, root)
        self.assertEqual(errors, [])
        before, after = kb_before["loci"][rsid], kb_after["loci"][rsid]
        self.assertEqual(after["evidence"]["clinvar"]["stars"], 4)
        for key in ("interpretations", "limitation"):
            self.assertEqual(json.dumps(before[key], sort_keys=True), json.dumps(after[key], sort_keys=True), key)
        gene = self.curation["loci"][rsid]["gene"]
        self.assertEqual(
            json.dumps(kb_before["genes"][gene], sort_keys=True), json.dumps(kb_after["genes"][gene], sort_keys=True)
        )
        # The derived tier did change with the imported stars, which is the point of keeping them apart.
        self.assertEqual(before["evidence_tier"], "Tier B")
        self.assertEqual(after["evidence_tier"], "Tier A")

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
