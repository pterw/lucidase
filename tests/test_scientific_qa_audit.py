"""
Scientific and architectural QA audit, as collected tests
=========================================================
Each test asserts the CORRECT behaviour for one audit domain of the desktop pipeline. Domains the
shared vectors already cover (palindromic SNP strand handling, the allele rules, the APOE
state machine on counts, the inheritance arithmetic) live in tests/vectors/*.json and run through
tests/test_vectors.py, so they are not repeated here:

 1. Build coordinate divergence (GRCh37 vs GRCh38) and a headerless file
 2. rsID is not immutable identity: duplicates, and coordinate-only VCF records
 4. VCF is not 23andMe with tabs
 5. Variant normalisation and coordinate identity for an indel
 6. APOE end to end from plus-strand genotypes, and the single-SNP trap
 7. Sex-chromosome signal evaluation
10. Evidence provenance in the KB
12. CPIC star-allele limitation (single-variant wild type is not a metabolizer phenotype)
13. Knowledge-base join collisions
14. Zero-knowledge network isolation of the annotation path
"""

from __future__ import annotations

import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genomic_parser import compute_qc, parse_genotype_file
from test_genomic_pipeline import make_annotator, pipeline_kb_json
from variant_annotator import KbSchemaError, validate_kb

VCF_HEAD = "##fileformat=VCFv4.2\n##reference={build}\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS\n"


class TestScientificAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.annotator = make_annotator()
        cls.kb = cls.annotator.kb

    def gt(self, rsid, alt_count):
        locus = self.kb.loci[rsid]
        return {0: locus["ref"] * 2, 1: locus["ref"] + locus["alt"], 2: locus["alt"] * 2}[alt_count]

    def row(self, report, rsid):
        return next(r for r in report.records if r.rsid == rsid)

    # [1] ---------------------------------------------------------------------
    def test_headerless_file_has_unknown_build_and_still_matches_by_rsid(self):
        # GRCh38 coordinates in a file with no build statement: the build is "unknown", never assumed.
        text = "rs429358\t19\t44908684\tTT\nrs7412\t19\t44908822\tCC\n"
        result = parse_genotype_file(text)
        self.assertEqual(result.build, "unknown")
        report = self.annotator.annotate_genome(result)
        apoe = self.row(report, "APOE-STATUS")
        self.assertEqual(apoe.raw["diplotype"], "e3/e3")
        self.assertEqual(apoe.pos, 44908684)  # the file's own position, not a guessed build's

    # [2] ---------------------------------------------------------------------
    def test_conflicting_duplicate_lines_are_never_resolved_by_last_wins(self):
        text = "rs429358\t19\t45411941\tTT\nrs429358\t19\t45411941\tCC\nrs7412\t19\t45412079\tCC\n"
        result = parse_genotype_file(text)
        self.assertEqual(len(result.calls), 3)  # both rs429358 lines are kept
        apoe = self.row(self.annotator.annotate_genome(result), "APOE-STATUS")
        self.assertIsNone(apoe.raw["diplotype"])  # not e4/e4 (last line) and not e3/e3 (first line)
        self.assertEqual(apoe.coverage_state, "insufficient_evidence")
        self.assertIn("genotype not interpretable", apoe.reason)

    def test_coordinate_only_vcf_record_matches_by_position_in_the_files_build(self):
        locus = self.kb.loci["rs429358"]
        row = f"19\t{locus['pos_grch37']}\t.\t{locus['ref']}\t{locus['alt']}\t99\tPASS\t.\tGT\t1/1\n"
        result = parse_genotype_file(VCF_HEAD.format(build="GRCh37") + row)
        self.assertIsNone(result.calls[0].rsid)
        apoe_component = next(
            r for r in self.annotator.annotate_genome(result).records if r.rsid == "APOE-STATUS"
        )
        e4_record = apoe_component.raw["components"][0]
        self.assertEqual((e4_record["rsid"], e4_record["altCount"]), ("rs429358", 2))

    # [4] ---------------------------------------------------------------------
    def test_vcf_edge_cases_decode_to_the_right_alleles(self):
        cases = {
            "phased 0|1": ("19\t45411941\trs429358\tT\tC\t99\tPASS\t.\tGT\t0|1", ["T", "C"]),
            "unphased 0/1": ("19\t45411941\trs429358\tT\tC\t99\tPASS\t.\tGT\t0/1", ["T", "C"]),
            "haploid on X": ("X\t1000\trs_hap\tA\tG\t99\tPASS\t.\tGT\t1", ["G"]),
            "multiallelic 1/2": ("1\t2000\trs_multi\tA\tC,G\t99\tPASS\t.\tGT\t1/2", ["C", "G"]),
            "missing ./.": ("1\t3000\trs_miss\tA\tG\t99\tPASS\t.\tGT\t./.", None),
            "partial 0/.": ("1\t4000\trs_part\tA\tG\t99\tPASS\t.\tGT\t0/.", None),
            "multi-format GT:DP:GQ": ("1\t5000\trs_fmt\tA\tG\t99\tPASS\t.\tGT:DP:GQ\t0/1:30:99", ["A", "G"]),
            "deletion": ("1\t6000\trs_del\tTC\tT\t99\tPASS\t.\tGT\t0/1", ["TC", "T"]),
        }
        for name, (line, expected) in cases.items():
            with self.subTest(name=name):
                (call,) = parse_genotype_file(VCF_HEAD.format(build="GRCh38") + line + "\n").calls
                self.assertEqual(call.alleles, expected)

    # [5] ---------------------------------------------------------------------
    def test_normalised_indel_matches_by_position_and_sequence(self):
        locus = self.kb.loci["rs113993960"]
        row = f"{locus['chrom']}\t{locus['pos_grch38']}\t.\t{locus['ref']}\t{locus['alt']}\t99\tPASS\t.\tGT\t0/1\n"
        report = self.annotator.annotate_genome(parse_genotype_file(VCF_HEAD.format(build="GRCh38") + row))
        self.assertEqual(self.row(report, "rs113993960").alt_count, 1)
        # An un-normalised representation of the same site (no shared anchor) is not guessed at.
        other = f"{locus['chrom']}\t{locus['pos_grch38']}\t.\tCT\tC\t99\tPASS\t.\tGT\t0/1\n"
        report = self.annotator.annotate_genome(parse_genotype_file(VCF_HEAD.format(build="GRCh38") + other))
        found = self.row(report, "rs113993960")
        self.assertIsNone(found.alt_count)
        self.assertEqual(found.coverage_state, "insufficient_evidence")

    # [6] ---------------------------------------------------------------------
    def test_apoe_end_to_end_from_plus_strand_genotypes(self):
        expected = {
            (0, 0): "e3/e3", (1, 0): "e3/e4", (2, 0): "e4/e4",
            (0, 1): "e2/e3", (0, 2): "e2/e2", (1, 1): "e2/e4",
            (2, 1): "atypical", (1, 2): "atypical", (2, 2): "atypical",
        }
        for (e4, e2), diplotype in expected.items():
            with self.subTest(e4=e4, e2=e2):
                text = f"# build 37\nrs429358\t19\t45411941\t{self.gt('rs429358', e4)}\nrs7412\t19\t45412079\t{self.gt('rs7412', e2)}\n"
                apoe = self.row(self.annotator.annotate_genome(parse_genotype_file(text)), "APOE-STATUS")
                self.assertEqual(apoe.raw["diplotype"], diplotype)

    def test_single_apoe_snp_never_presumes_e3_e3(self):
        text = f"# build 37\nrs429358\t19\t45411941\t{self.gt('rs429358', 0)}\n"
        apoe = self.row(self.annotator.annotate_genome(parse_genotype_file(text)), "APOE-STATUS")
        self.assertIsNone(apoe.raw["diplotype"])  # could be e2/e2, e2/e3 or e3/e3
        self.assertEqual(apoe.coverage_state, "not_tested_by_array")
        self.assertNotIn("e3/e3", apoe.genotype)

    # [7] ---------------------------------------------------------------------
    def test_sex_chromosome_signal_describes_x_heterozygosity_only(self):
        def x(n, het_every=None):  # every `het_every`-th X marker is heterozygous; None means none are
            return [
                f"rsX{i}	X	{1000 + i * 100}	{'AG' if het_every and i % het_every == 0 else 'AA'}"
                for i in range(n)
            ]

        def y(n):
            return [f"rsY{i}\tY\t{2000 + i * 100}\tGG" for i in range(n)]

        def signal(rows):
            return compute_qc(parse_genotype_file("# 23andMe\n" + "\n".join(rows) + "\n"))["sex_signal"]

        two_x = "X heterozygosity consistent with two X chromosomes"
        one_x = "X heterozygosity consistent with one X chromosome"
        self.assertEqual(signal(x(60, 3)), two_x)  # female-pattern
        self.assertEqual(signal(x(60) + y(15)), one_x)  # male-pattern (no X het, Y calls)
        self.assertEqual(signal(x(60, 3) + y(15)), two_x)  # Y calls do not turn a two-X signal into "male"
        self.assertEqual(signal(x(60)), one_x)  # X0 looks the same as XY on X alone
        self.assertEqual(signal(x(3)), "Indeterminate (too few X markers)")
        for text in (two_x, one_x):
            for banned in ("male", "karyotype", "xx", "xy", "klinefelter", "turner"):
                self.assertNotIn(banned, text.lower())

    # [10] --------------------------------------------------------------------
    def test_in_memory_kb_clinvar_block_has_exactly_its_keys_and_every_block_has_provenance(self):
        for rsid, locus in self.kb.loci.items():
            for name in ("clinvar", "gnomad"):
                self.assertIn("provenance", locus["evidence"][name], f"{rsid} {name}")
            clinvar = locus["evidence"]["clinvar"]
            self.assertEqual(sorted(k for k in clinvar if k != "provenance"),
                             ["accession", "review_status", "significance", "stars"], rsid)
            pli = locus["evidence"]["gnomad"]["pli"]
            self.assertTrue(pli is None or 0 <= pli <= 1, f"{rsid} pLI {pli}")

    # [12] --------------------------------------------------------------------
    def test_single_star_allele_wildtype_is_not_a_metabolizer_phenotype(self):
        text = f"# build 37\nrs4244285\t10\t96541616\t{self.gt('rs4244285', 0)}\n"
        row = self.row(self.annotator.annotate_genome(parse_genotype_file(text)), "rs4244285")
        self.assertEqual(row.coverage_state, "supported_not_observed")
        self.assertEqual(row.category, "Not detected")
        self.assertIsNotNone(row.limitation)  # the single-variant / star-allele caveat is carried
        shown = (row.phenotype + " " + row.limitation).lower()
        self.assertNotIn("*1/*1", shown)
        self.assertNotIn("normal metabolizer", shown)
        self.assertIn("cannot", shown)

    # [13] --------------------------------------------------------------------
    def test_join_collisions_are_rejected_by_the_loader(self):
        data = pipeline_kb_json()
        a, b = sorted(data["loci"])[:2]
        for field in ("pos_grch37", "pos_grch38"):
            collided = pipeline_kb_json()
            collided["loci"][b]["chrom"] = collided["loci"][a]["chrom"]
            collided["loci"][b][field] = collided["loci"][a][field]
            with self.subTest(field=field), self.assertRaises(KbSchemaError):
                validate_kb(collided)

    def test_positions_in_the_in_memory_kb_are_unique_per_build(self):
        for field in ("pos_grch37", "pos_grch38"):
            seen = [(l["chrom"], l[field]) for l in self.kb.loci.values()]
            self.assertEqual(len(seen), len(set(seen)), field)

    # [14] --------------------------------------------------------------------
    def test_annotation_path_makes_no_network_or_subprocess_calls(self):
        text = f"# build 37\nrs429358\t19\t45411941\t{self.gt('rs429358', 1)}\nrs7412\t19\t45412079\t{self.gt('rs7412', 0)}\n"
        boom = AssertionError("the annotation path must not touch the network or start a process")
        with mock.patch.object(socket.socket, "connect", side_effect=boom), mock.patch.object(
            socket, "create_connection", side_effect=boom
        ), mock.patch.object(subprocess, "run", side_effect=boom), mock.patch.object(
            subprocess, "Popen", side_effect=boom
        ):
            report = self.annotator.annotate_genome(parse_genotype_file(text))
            self.annotator.summarize_annotations(report)
        self.assertIsNone(self.annotator._biotools)  # the external-service orchestrator was never created


if __name__ == "__main__":
    unittest.main()
