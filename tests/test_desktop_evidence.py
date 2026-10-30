"""Desktop APOE evidence, the not-detected statement, the ACMG gene count and the CLI report (S4-F2b).

S4a-C-2 (P1-068): the APOE row carries per-component evidence and no evidence of its own.
S4a-C-3 (P1-069): a wild-type row says how many variants were tested in its gene.
S4c-C-4 (P1-078): the headless clinical report uses the GUI's serialiser.
The wording itself is pinned by tests/vectors/statements.json (shared with the web app).
"""

import contextlib
import csv
import io
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import debruijn.debruijn_explorer as debruijn_explorer  # noqa: E402
import gui  # noqa: E402
from genomic_parser import parse_genotype_file  # noqa: E402
from test_gui_genome import analyse, make_app  # noqa: E402
from variant_annotator import VariantAnnotator  # noqa: E402

HEADER = "# rsid\tchromosome\tposition\tgenotype\n"
# APOE e3/e4 (rs429358 CT, rs7412 CC), CFTR F508del wild type (code I/I), DPYD wild type, one HFE locus wild type.
CFTR = "rs113993960"


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.annotator = VariantAnnotator()
        cls.kb = cls.annotator.kb

    def line(self, rsid, genotype):
        locus = self.kb.loci[rsid]
        return f"{rsid}\t{locus['chrom']}\t{locus['pos_grch37']}\t{genotype}\n"

    def wild_type(self, rsid):
        locus = self.kb.loci[rsid]
        codes = locus.get("allele_codes")
        if codes:
            code = next(k for k, v in codes.items() if v == "ref")
            return self.line(rsid, code + code)
        return self.line(rsid, locus["ref"] * 2)

    def het(self, rsid):
        locus = self.kb.loci[rsid]
        return self.line(rsid, locus["ref"] + locus["alt"])

    def report(self, *lines):
        text = "# build 37\n" + HEADER + "".join(lines)
        return self.annotator.annotate_genome(parse_genotype_file(text))

    def row(self, report, gene):
        return next(r for r in report.records if r.gene == gene)

    def tmpdir(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return Path(d)


class ApoeEvidencePerComponent(Fixture):
    def setUp(self):
        self.report_ = self.report(self.het("rs429358"), self.wild_type("rs7412"))
        self.apoe = self.row(self.report_, "APOE")

    def test_the_row_has_no_evidence_of_its_own(self):
        self.assertEqual(self.apoe.raw["diplotype"], "e3/e4")
        self.assertIsNone(self.apoe.review_stars)
        self.assertIsNone(self.apoe.gnomad_af)
        self.assertIsNone(self.apoe.gnomad_pli)

    def test_row_tier_is_the_shared_tier_when_the_components_agree(self):
        tiers = {c["evidence_tier"] for c in self.apoe.component_evidence}
        self.assertEqual(tiers, {"Tier A"})
        self.assertEqual(self.apoe.evidence_tier, "Tier A")

    def test_row_tier_is_the_labelled_join_when_the_components_disagree(self):
        with mock.patch.dict(self.kb.loci["rs7412"], {"evidence_tier": "Tier C"}):
            apoe = self.row(self.report(self.het("rs429358"), self.wild_type("rs7412")), "APOE")
        self.assertEqual([c["evidence_tier"] for c in apoe.component_evidence], ["Tier A", "Tier C"])
        self.assertEqual(apoe.evidence_tier, "rs429358: Tier A · rs7412: Tier C")

    def test_each_component_carries_its_own_evidence(self):
        got = {c["rsid"]: c for c in self.apoe.component_evidence}
        self.assertEqual(list(got), ["rs429358", "rs7412"])
        for rsid, c in got.items():
            ev = self.kb.loci[rsid]["evidence"]
            self.assertEqual(c["review_stars"], ev["clinvar"]["stars"])
            self.assertEqual(c["gnomad_af"], ev["gnomad"]["af"])
            self.assertEqual(c["gnomad_pli"], ev["gnomad"]["pli"])
            self.assertEqual(c["evidence_tier"], self.kb.loci[rsid]["evidence_tier"])
        self.assertNotEqual(got["rs429358"]["review_stars"], got["rs7412"]["review_stars"])

    def test_a_standalone_row_has_no_component_evidence(self):
        report = self.report(self.wild_type("rs1800562"))
        self.assertIsNone(self.row(report, "HFE").component_evidence)

    def test_detail_pane_labels_each_component(self):
        app = make_app()
        report = analyse(app, "# build 37\n" + HEADER + self.het("rs429358") + self.wild_type("rs7412"))
        app.genome_tree.picked = app.genome_records.index(self.row(report, "APOE"))
        app._genome_row_selected(None)
        detail = app.genome_detail_text.content
        self.assertIn("rs429358: 1 of 4 review stars · rs7412: 3 of 4 review stars", detail)
        self.assertIn("rs429358: 14.85% · rs7412: 7.42%", detail)
        self.assertIn("rs429358: Tier A · rs7412: Tier A", detail)
        self.assertNotIn("2 of 4 review stars", detail)
        self.assertNotIn("★", detail)

    def test_csv_and_markdown_show_the_components_values(self):
        csv_path, md_path = self.tmpdir() / "r.csv", self.tmpdir() / "r.md"
        gui.write_clinical_csv(str(csv_path), self.report_.records, "f.txt", "rel")
        with open(csv_path, newline="", encoding="utf-8") as f:
            row = next(r for r in csv.DictReader(f) if r["gene"] == "APOE")
        self.assertEqual(row["review_stars"], "1;3")
        self.assertEqual(row["evidence_tier"], "Tier A;Tier A")
        af = [float(x) for x in row["gnomad_af"].split(";")]
        self.assertEqual(af, [self.kb.loci[r]["evidence"]["gnomad"]["af"] for r in ("rs429358", "rs7412")])
        self.assertEqual(row["rsid"], "APOE (rs429358 + rs7412)")
        parse = parse_genotype_file("# build 37\n" + HEADER + self.het("rs429358"))
        qc = {"call_rate": 1.0, "qc_note": "", "sex_signal": "n/a"}
        gui.write_clinical_markdown(str(md_path), self.report_.records, parse, qc, "f.txt", "rel")
        line = next(x for x in md_path.read_text(encoding="utf-8").splitlines() if "APOE (rs429358" in x)
        self.assertIn("rs429358: 1 of 4 review stars · rs7412: 3 of 4 review stars", line)
        self.assertNotIn("★", line)


class NotDetectedStatement(Fixture):
    def test_wild_type_row_states_how_many_variants_were_tested_in_its_gene(self):
        report = self.report(self.wild_type(CFTR))
        self.assertEqual(
            self.row(report, "CFTR").not_detected_statement,
            f"{CFTR} variant not detected (1 variant tested in CFTR)",
        )

    def test_array_gaps_are_not_counted_as_tested(self):
        one = next(r for r in self.report(self.wild_type("rs1800562")).records if r.rsid == "rs1800562")
        self.assertIn("(1 variant tested in HFE)", one.not_detected_statement)
        both = self.report(self.wild_type("rs1800562"), self.wild_type("rs1799945"))
        statements = [r.not_detected_statement for r in both.records if r.gene == "HFE" and r.not_detected_statement]
        self.assertEqual(len(statements), 2)
        for s in statements:
            self.assertIn("(2 variants tested in HFE)", s)

    def test_a_variant_present_or_untested_row_makes_no_not_detected_claim(self):
        report = self.report(self.het("rs1800562"))
        for r in report.records:
            if r.gene == "HFE" and r.rsid == "rs1800562":
                self.assertIsNone(r.not_detected_statement)
            if r.coverage_state == "not_tested_by_array":
                self.assertIsNone(r.not_detected_statement)

    def test_apoe_wild_type_names_both_alleles_and_both_components(self):
        report = self.report(self.wild_type("rs429358"), self.wild_type("rs7412"))
        self.assertEqual(
            self.row(report, "APOE").not_detected_statement,
            "APOE ε2 and ε4 alleles not detected (2 variants tested in APOE)",
        )

    def test_gui_detail_csv_and_markdown_carry_the_statement(self):
        app = make_app()
        text = "# build 37\n" + HEADER + self.wild_type(CFTR)
        report = analyse(app, text)
        statement = self.row(report, "CFTR").not_detected_statement
        app.genome_tree.picked = app.genome_records.index(self.row(report, "CFTR"))
        app._genome_row_selected(None)
        self.assertIn(statement, app.genome_detail_text.content)
        out = self.tmpdir() / "r.csv"
        gui.write_clinical_csv(str(out), report.records, "f.txt", "rel")
        with open(out, newline="", encoding="utf-8") as f:
            row = next(r for r in csv.DictReader(f) if r["gene"] == "CFTR")
        self.assertEqual(row["not_detected_statement"], statement)
        self.assertEqual(row["sample_observation"], "wild_type")


class AcmgCountIsDistinctGenes(Fixture):
    def test_two_variants_in_one_acmg_gene_are_one_actionable_gene(self):
        report = self.report(self.het("rs1800562"), self.het("rs1799945"))
        summary = self.annotator.summarize_annotations(report)
        self.assertEqual(len(summary["acmg_findings"]), 2)
        self.assertEqual(summary["acmg_actionable_findings"], 1)


class CliReportUsesTheGuiSerialiser(Fixture):
    SAMPLE = (
        "# build 37\n" + HEADER
        + "rs3918290\t1\t97915614\tCC\nrs4988235\t2\t136608646\tGG\n"
        + "rs429358\t19\t45411941\tCT\nrs7412\t19\t45412079\tCC\n"
    )

    def run_cli(self, out: Path):
        src = self.tmpdir() / "mine.txt"
        src.write_text(self.SAMPLE, encoding="utf-8")
        args = types.SimpleNamespace(genome=str(src), clinical_report=str(out))
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = debruijn_explorer.run_headless(args)
        self.assertEqual(code, 0)
        return src, stdout.getvalue()

    def test_csv_matches_the_gui_export_and_carries_the_row_state(self):
        out = self.tmpdir() / "r.csv"
        src, _ = self.run_cli(out)
        report = self.annotator.annotate_genome(parse_genotype_file(self.SAMPLE, "mine.txt"))
        expected = self.tmpdir() / "gui.csv"
        gui.write_clinical_csv(str(expected), report.records, "mine.txt", report.kb_release)
        self.assertEqual(out.read_bytes(), expected.read_bytes())
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        dpyd = next(r for r in rows if r["gene"] == "DPYD")
        self.assertEqual(dpyd["coverage_state"], "supported_not_observed")
        self.assertEqual(dpyd["sample_observation"], "wild_type")
        self.assertTrue(dpyd["limitation"])
        self.assertIn("(1 variant tested in DPYD)", dpyd["not_detected_statement"])
        untested = next(r for r in rows if r["coverage_state"] == "not_tested_by_array")
        self.assertEqual(untested["sample_observation"], "call_unavailable")
        self.assertTrue(untested["reason"])

    def test_markdown_carries_state_limitation_statement_and_the_caveat(self):
        out = self.tmpdir() / "r.md"
        self.run_cli(out)
        text = out.read_text(encoding="utf-8")
        report = self.annotator.annotate_genome(parse_genotype_file(self.SAMPLE, "mine.txt"))
        dpyd = self.row(report, "DPYD")
        self.assertIn(gui.REPORT_CAVEAT, text)
        self.assertIn(dpyd.limitation, text)
        self.assertIn(dpyd.not_detected_statement, text)
        # The report says the plain result word; the data key stays in the CSV only.
        dpyd_line = next(x for x in text.splitlines() if x.startswith(f"| **{dpyd.rsid}** |"))
        self.assertIn("| Not found |", dpyd_line)
        self.assertNotIn("supported_not_observed", text)
        self.assertIn("call_unavailable", text)
        self.assertIn("mine.txt", text)
        self.assertNotIn("APOE-STATUS", text)
        self.assertIn("APOE (rs429358 + rs7412)", text)

    def test_stdout_lists_limitation_and_statement(self):
        out = self.tmpdir() / "r.md"
        _, stdout = self.run_cli(out)
        report = self.annotator.annotate_genome(parse_genotype_file(self.SAMPLE, "mine.txt"))
        dpyd = self.row(report, "DPYD")
        self.assertIn(dpyd.limitation, stdout)
        self.assertIn(dpyd.not_detected_statement, stdout)

    def test_stdout_says_the_result_words_and_the_stars_in_words(self):
        _, stdout = self.run_cli(self.tmpdir() / "r.md")
        report = self.annotator.annotate_genome(parse_genotype_file(self.SAMPLE, "mine.txt"))
        cov = self.annotator.summarize_annotations(report)["coverage"]
        self.assertIn(
            f"  Not on your chip:....... {cov['not_tested_by_array_count']} of {cov['total_loci']} loci\n", stdout
        )
        self.assertIn(f"  Unclear:................ {cov['insufficient_evidence_count']}\n", stdout)
        dpyd = next(x for x in stdout.splitlines() if "[DPYD" in x)
        self.assertIn("| Not found |", dpyd)
        mcm6 = next(x for x in stdout.splitlines() if "[MCM6" in x)
        self.assertIn("(0 of 4 review stars)", mcm6)
        for old in ("★", "0 stars", "Not tested by this file", "Insufficient evidence", "supported_", "not_tested_"):
            self.assertNotIn(old, stdout)


if __name__ == "__main__":
    unittest.main()
