"""
Adversarial and fuzz tests for the desktop parser and annotator.

Rules asserted (AGENTS.md section 3, fail fast and fail closed):
- Input that is not a recognised genotype file raises UnsupportedFormatError. It is never guessed at
  and never raises anything else.
- Input that is recognised parses without raising, however corrupt some rows are. Corrupt rows are
  counted in `skipped_malformed`, not silently turned into calls.
- Whatever the file contains, the annotator returns exactly one finding per KB locus (APOE as one
  row), so a hostile file cannot make a locus vanish.

The fuzz test uses a fixed seed, so a failure reproduces.
"""

from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genomic_parser import UnsupportedFormatError, parse_genotype_file
from test_genomic_pipeline import make_annotator

NOT_A_GENOTYPE_FILE = {
    "empty_file": "",
    "only_newlines": "\n" * 500,
    "header_only_then_garbage": "# build 37\n# rsid\tchr\tpos\tgenotype\n" + "\t".join(["invalid"] * 20),
    "binary_null_bytes": "\x00\x00\x00\xff\xfe\x00\x1b\x5b",
    "html_error_page": "<html><head><title>500 Internal Server Error</title></head><body>Crash</body></html>",
    "json_payload": json.dumps({"user": "victim", "dna": [1, 2, 3]}),
}

RECOGNISED_BUT_HOSTILE = {
    "sql_injection": "rs123\t1\t100\t'; DROP TABLE users; --\nrs456\t' OR '1'='1\t200\tAA",
    "massive_single_line": "rs429358\t19\t45411941\tCC\t" + ("A" * 200000),
    "non_standard_chromosomes": "rs1\tchrUn_gl000220\t1000\tAA\nrs2\tM\t200\tCC\nrs3\t25\t300\tGG",
    "mixed_corrupt_and_valid": (
        "# 23andMe sample with corruption\n"
        "rubbish line\n"
        "rs429358\t19\t45411941\tCC\n"
        "bad\t\t\t\n"
        "rs7412\t19\t45412079\tCC\n"
        "rs1800562\t6\t26093141\tAG\n"
    ),
}

VALID_SEED_FILE = (
    "# build 37\n"
    "# rsid\tchromosome\tposition\tgenotype\n"
    "rs429358\t19\t45411941\tCT\n"
    "rs7412\t19\t45412079\tCC\n"
    "rs1800562\t6\t26093141\tAG\n"
    "rs1799945\t6\t26091179\tCG\n"
    "rs6025\t1\t169519049\tCT\n"
    "rs113993960\t7\t117199644\tDI\n"
    "rs9999999\t1\t50000000\t--\n"
)


class TestAdversarialInput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.annotator = make_annotator()
        cls.expected_rows = len(cls.annotator.kb.loci) - 1  # two APOE components become one row

    def test_non_genotype_input_raises_unsupported_format_error(self):
        for name, text in NOT_A_GENOTYPE_FILE.items():
            with self.subTest(name=name):
                with self.assertRaises(UnsupportedFormatError):
                    parse_genotype_file(text)

    def test_hostile_but_recognised_input_parses_without_error_and_never_fabricates_findings(self):
        for name, text in RECOGNISED_BUT_HOSTILE.items():
            with self.subTest(name=name):
                result = parse_genotype_file(text)
                report = self.annotator.annotate_genome(result)
                self.assertEqual(len(report.records), self.expected_rows)
                self.assertEqual(
                    result.stats.data_rows, len(result.calls) + result.stats.skipped_malformed
                )

    def test_massive_line_and_sql_text_are_malformed_rows_not_calls(self):
        sql = parse_genotype_file(RECOGNISED_BUT_HOSTILE["sql_injection"])
        self.assertEqual(sql.stats.skipped_malformed, 1)  # the row whose genotype is SQL text
        massive = parse_genotype_file(RECOGNISED_BUT_HOSTILE["massive_single_line"])
        self.assertEqual(massive.calls, [])
        self.assertEqual(massive.stats.skipped_malformed, 1)

    def test_corrupt_rows_between_valid_ones_are_counted_and_valid_ones_survive(self):
        result = parse_genotype_file(RECOGNISED_BUT_HOSTILE["mixed_corrupt_and_valid"])
        self.assertEqual([c.rsid for c in result.calls], ["rs429358", "rs7412", "rs1800562"])
        self.assertEqual(result.stats.skipped_malformed, 2)
        report = self.annotator.annotate_genome(result)
        apoe = next(r for r in report.records if r.rsid == "APOE-STATUS")
        self.assertEqual(apoe.raw["diplotype"], "e4/e4")

    def test_seeded_random_mutations_never_crash_and_never_drop_a_locus(self):
        rng = random.Random(20261002)
        alphabet = "ACGTDI-\t,;\"' \x00﻿#rs0123456789\n"
        for case in range(300):
            lines = VALID_SEED_FILE.split("\n")
            for _ in range(rng.randint(1, 6)):
                op = rng.choice(["drop_line", "dup_line", "garble_char", "insert_junk", "swap_lines", "cut_tail"])
                i = rng.randrange(len(lines))
                if op == "drop_line":
                    del lines[i]
                elif op == "dup_line":
                    lines.insert(i, lines[i])
                elif op == "garble_char" and lines[i]:
                    j = rng.randrange(len(lines[i]))
                    lines[i] = lines[i][:j] + rng.choice(alphabet) + lines[i][j + 1:]
                elif op == "insert_junk":
                    lines.insert(i, "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40))))
                elif op == "swap_lines":
                    k = rng.randrange(len(lines))
                    lines[i], lines[k] = lines[k], lines[i]
                elif op == "cut_tail":
                    lines = lines[: max(1, i)]
                if not lines:
                    lines = [""]
            text = "\n".join(lines)
            try:
                result = parse_genotype_file(text)
            except UnsupportedFormatError:
                continue
            except Exception as err:  # pragma: no cover - the assertion message is the point
                self.fail(f"case {case}: {type(err).__name__}: {err}\n{text!r}")
            report = self.annotator.annotate_genome(result)
            self.assertEqual(len(report.records), self.expected_rows, f"case {case}: {text!r}")
            for row in report.records:
                # No row may claim a variant it could not read.
                if row.alt_count is None and row.rsid != "APOE-STATUS":  # atypical APOE is the one exception
                    self.assertNotEqual(row.sample_observation, "variant_present", f"case {case} {row.rsid}")


if __name__ == "__main__":
    unittest.main()
