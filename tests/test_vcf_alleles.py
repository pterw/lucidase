"""Regression pins for VCF no-call genotypes in genomic_parser._vcf_alleles (docs/HANDOFF.md section 8).

A no-call ("." or "./.") with a real string allele table must come back as None (no call), never as an empty
allele list or the malformed sentinel: None is what makes the record "Not on your chip" instead of a genotype.
"""

import unittest

from genomic_parser import _MALFORMED, _vcf_alleles


class TestVcfNoCalls(unittest.TestCase):
    TABLE = ["A", "G"]

    def test_whole_no_calls_are_none(self):
        for gt in (".", "./.", ".|."):
            with self.subTest(gt=gt):
                self.assertIsNone(_vcf_alleles(gt, self.TABLE))

    def test_a_half_no_call_is_none_not_a_single_allele(self):
        for gt in ("./1", "0/.", ".|0"):
            with self.subTest(gt=gt):
                self.assertIsNone(_vcf_alleles(gt, self.TABLE))

    def test_a_called_genotype_still_reads_its_alleles(self):
        self.assertEqual(_vcf_alleles("0/1", self.TABLE), ["A", "G"])
        self.assertEqual(_vcf_alleles("1|1", self.TABLE), ["G", "G"])

    def test_a_bad_index_is_malformed_not_a_no_call(self):
        self.assertIs(_vcf_alleles("0/2", self.TABLE), _MALFORMED)
        self.assertIs(_vcf_alleles("0/x", self.TABLE), _MALFORMED)


if __name__ == "__main__":
    unittest.main()
