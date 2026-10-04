"""Desktop GUI genome view: rows, exports, failure state, load path (S4b-C-8 to C-12, C-14, C-16).

The Tk callbacks run on a stub app (no display): `ExplorerApp.__new__` plus recording widget stubs.
"""

import csv
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gui  # noqa: E402
from genomic_parser import parse_genotype_file  # noqa: E402
from variant_annotator import RESULT_WORDS, VariantAnnotator  # noqa: E402

HEADER = "# rsid\tchromosome\tposition\tgenotype\n"
# DPYD wild type carries a limitation; MCM6 (rs4988235) has 0 ClinVar stars and a caveat.
SAMPLE = (
    HEADER
    + "rs3918290\t1\t97915614\tCC\nrs4988235\t2\t136608646\tGG\nrs429358\t19\t45411941\tCC\nrs7412\t19\t45412079\tCC\n"
)


class FakeTree:
    def __init__(self):
        self.rows = []
        self.picked = 0

    def delete(self, *_ids):
        self.rows = []

    def get_children(self):
        return list(range(len(self.rows)))

    def insert(self, _parent, _where, values):
        self.rows.append(tuple(values))

    def selection(self):
        return (0,)

    def index(self, _item):
        return self.picked


class FakeText:
    def __init__(self, content=""):
        self.content = content

    def configure(self, **_):
        pass

    def delete(self, *_):
        self.content = ""

    def insert(self, _where, text):
        self.content += text

    def get(self, *_):
        return self.content


class FakeVar:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class FakeButton:
    def __init__(self):
        self.disabled = False

    def state(self, spec):
        self.disabled = "disabled" in spec


def make_app():
    app = gui.ExplorerApp.__new__(gui.ExplorerApp)
    app.genome_tree = FakeTree()
    app.genome_detail_text = FakeText()
    app.nb = types.SimpleNamespace(tabs=lambda: [], tab=lambda *_: {}, select=lambda *_: None)
    app.text = FakeText()
    app.mode = FakeVar("genome")
    app.statuses = []
    app.set_status = lambda msg, error=False: app.statuses.append((msg, error))
    app._mode_changed = lambda: None
    app._stop_play = lambda: None
    app.export_clinical_btn = FakeButton()
    app.genome_records = []
    app.sample_qc = None
    app.sample_parse = None
    app.genome_source = ""
    app.genome_kb_release = ""
    app.genome_path = None
    app.genome_preview = ""
    return app


def analyse(app, text=SAMPLE):
    result = parse_genotype_file(text)
    report = VariantAnnotator().annotate_genome(result)
    app._populate_genome_results(result, report)
    return report


def export(app, path):
    with mock.patch.object(gui, "filedialog", types.SimpleNamespace(asksaveasfilename=lambda **_: str(path))):
        app.export_clinical_report()


class TmpMixin:
    def tmpdir(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return Path(d)


class RowsAndExports(TmpMixin, unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.report = analyse(self.app)
        self.dpyd = next(r for r in self.report.records if r.gene == "DPYD")
        self.mcm6 = next(r for r in self.report.records if r.gene == "MCM6")

    def row(self, gene):
        return next(v for v in self.app.genome_tree.rows if v[1] == gene)

    def test_fixture_has_a_limitation_a_caveat_and_zero_stars(self):
        self.assertTrue(self.dpyd.limitation)
        self.assertTrue(self.mcm6.caveats)
        self.assertEqual(self.mcm6.review_stars, 0)

    def test_table_row_carries_the_limitation(self):
        self.assertIn(self.dpyd.limitation, self.row("DPYD"))

    def test_table_phenotype_is_not_cut(self):
        row = self.row("DPYD")
        self.assertIn(self.dpyd.phenotype, row)
        self.assertFalse(any(str(c).endswith("…") for c in row))

    def test_csv_carries_limitation_and_caveats(self):
        out = self.tmpdir() / "r.csv"
        export(self.app, out)
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        d = next(r for r in rows if r["gene"] == "DPYD")
        self.assertEqual(d["limitation"], self.dpyd.limitation)
        m = next(r for r in rows if r["gene"] == "MCM6")
        self.assertIn(self.mcm6.caveats[0], m["caveats"])

    def test_markdown_carries_limitation_and_caveats(self):
        out = self.tmpdir() / "r.md"
        export(self.app, out)
        text = out.read_text(encoding="utf-8")
        self.assertIn(self.dpyd.limitation, text)
        self.assertIn(self.mcm6.caveats[0], text)

    def test_zero_stars_is_a_value_in_table_and_markdown(self):
        self.assertIn("0 of 4 review stars", self.row("MCM6"))
        out = self.tmpdir() / "r.md"
        export(self.app, out)
        line = next(x for x in out.read_text(encoding="utf-8").splitlines() if "MCM6" in x)
        self.assertIn("0 of 4 review stars", line)

    def test_exports_name_the_file_and_the_kb_release(self):
        src = self.tmpdir() / "mine.txt"
        src.write_text(SAMPLE, encoding="utf-8")
        self.app._build_genome_file(str(src))
        for name in ("r.csv", "r.md"):
            out = self.tmpdir() / name
            export(self.app, out)
            text = out.read_text(encoding="utf-8")
            self.assertIn("mine.txt", text, name)
            self.assertIn(self.report.kb_release, text, name)

    def test_detail_shows_caveats_and_labels_magnitude_plainly(self):
        self.app.genome_tree.picked = self.app.genome_records.index(self.mcm6)
        self.app._genome_row_selected(None)
        detail = self.app.genome_detail_text.content
        self.assertIn(self.mcm6.caveats[0], detail)
        self.assertNotIn("Promethease", detail)
        self.assertIn("Magnitude", detail)

    def test_detail_labels_hand_entered_hpa_data(self):
        self.app.genome_tree.picked = self.app.genome_records.index(self.mcm6)
        self.app._genome_row_selected(None)
        detail = self.app.genome_detail_text.content
        source = self.mcm6.raw["evidence"]["hpa"]["provenance"]["source"]
        self.assertIn(source, detail)
        self.assertNotIn("Human Protein Atlas (HPA) Tissue Abundance", detail)

    def test_gui_text_does_not_present_hpa_as_verified_or_name_promethease(self):
        src = (ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertNotIn("Promethease", src)
        self.assertNotIn("Human Protein Atlas (HPA) tissue protein abundance", src)
        self.assertNotIn("ClinVar, HPA, PGx", src)


def web_result_labels() -> dict:
    """The label of each web result word, read from the view model's RESULT_WORDS table (no JS is run)."""
    src = (ROOT / "web" / "src" / "view-model.js").read_text(encoding="utf-8")
    block = re.search(r"export const RESULT_WORDS = deepFreeze\(\{(.*?)\n\}\);", src, re.S).group(1)
    return dict(re.findall(r"(\w+): \{\s*label: \"([^\"]+)\"", block))


# The desktop's old state and stars wording ("Detected" is checked on the significance itself: the banner says
# "Format Detected").
OLD_DESKTOP_WORDS = (
    "★", "/ 4 stars", "0 stars", "Not tested by this file", "Insufficient evidence",
    "supported and observed", "supported not observed", "not tested by array", "insufficient evidence",
)


class PlainWording(TmpMixin, unittest.TestCase):
    """The desktop says what the web view model says: the plain result words and "N of 4 review stars"."""

    def setUp(self):
        self.app = make_app()
        self.report = analyse(self.app)
        self.mcm6 = next(r for r in self.report.records if r.gene == "MCM6")

    def stars(self, n):
        return gui.stars_text(types.SimpleNamespace(component_evidence=None, review_stars=n))

    def test_result_words_are_the_web_labels(self):
        web = web_result_labels()
        self.assertEqual(
            web,
            {
                "supported_and_observed": "Found",
                "supported_not_observed": "Not found",
                "not_tested_by_array": "Not on your chip",
                "outside_coverage": "Not checked",
                "insufficient_evidence": "Unclear",
            },
        )
        self.assertEqual(RESULT_WORDS, web)

    def test_stars_are_said_as_n_of_4_review_stars(self):
        self.assertEqual(self.stars(0), "0 of 4 review stars")
        self.assertEqual(self.stars(1), "1 of 4 review stars")
        self.assertEqual(self.stars(3), "3 of 4 review stars")
        self.assertEqual(self.stars(4), "4 of 4 review stars")
        self.assertEqual(self.stars(None), gui.NOT_AVAILABLE)
        web = (ROOT / "web" / "src" / "view-model.js").read_text(encoding="utf-8")
        self.assertIn("`${stars} of 4 review stars`", web)

    def test_a_row_without_an_interpretation_says_its_result_word(self):
        bare = [r for r in self.report.records if r.raw["interpretation"] is None]
        self.assertTrue(bare)
        for r in bare:
            self.assertEqual(r.clinical_significance, RESULT_WORDS[r.coverage_state], r.rsid)

    def test_detail_pane_says_the_result_word_and_the_stars_in_words(self):
        self.app.genome_tree.picked = self.app.genome_records.index(self.mcm6)
        self.app._genome_row_selected(None)
        detail = self.app.genome_detail_text.content
        self.assertIn(f"Coverage:............... {RESULT_WORDS[self.mcm6.coverage_state]}\n", detail)
        self.assertIn("ClinVar Review Stars:... 0 of 4 review stars\n", detail)
        for old in OLD_DESKTOP_WORDS:
            self.assertNotIn(old, detail)

    def test_summary_banner_counts_under_the_result_words(self):
        banner = self.app.genome_detail_text.content
        cov = self.report.coverage
        self.assertIn(
            f"  Not on your chip:....... {cov['not_tested_by_array_count']} of {cov['total_loci']} loci\n", banner
        )
        self.assertIn(f"  Unclear:................ {cov['insufficient_evidence_count']}\n", banner)
        for old in OLD_DESKTOP_WORDS:
            self.assertNotIn(old, banner)

    def test_table_and_markdown_use_the_result_words(self):
        for row in self.app.genome_tree.rows:
            for old in OLD_DESKTOP_WORDS:
                self.assertNotIn(old, " ".join(map(str, row)))
        out = self.tmpdir() / "r.md"
        export(self.app, out)
        lines = out.read_text(encoding="utf-8").splitlines()
        for r in self.report.records:
            line = next(x for x in lines if x.startswith(f"| **{gui._md_cell(gui._row_label(r))}** |"))
            self.assertIn(f"| {RESULT_WORDS[r.coverage_state]} |", line)
            self.assertNotIn(r.coverage_state, line)
            for old in OLD_DESKTOP_WORDS:
                self.assertNotIn(old, line)

    def test_csv_keeps_the_data_keys(self):
        out = self.tmpdir() / "r.csv"
        export(self.app, out)
        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(tuple(reader.fieldnames), gui.CSV_COLUMNS)
            rows = list(reader)
        self.assertEqual({r["coverage_state"] for r in rows}, {r.coverage_state for r in self.report.records})
        self.assertEqual(next(r for r in rows if r["gene"] == "MCM6")["review_stars"], "0")

    def test_gui_source_has_no_star_glyphs(self):
        src = (ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertNotIn("★", src)
        self.assertNotIn("/ 4 stars", src)


class FailureClearsResults(TmpMixin, unittest.TestCase):
    def test_failed_text_analysis_clears_results_and_blocks_export(self):
        app = make_app()
        analyse(app)
        self.assertTrue(app.genome_tree.rows)
        app._build_genome_text("this is not a genotype file")
        self.assertEqual(app.genome_tree.rows, [])
        self.assertEqual(app.genome_records, [])
        self.assertIsNone(app.sample_qc)
        self.assertTrue(app.export_clinical_btn.disabled)
        self.assertTrue(app.statuses[-1][1])

    def test_failed_file_analysis_clears_results(self):
        app = make_app()
        analyse(app)
        app._build_genome_file(str(self.tmpdir() / "no_such_file.txt"))
        self.assertEqual(app.genome_tree.rows, [])
        self.assertEqual(app.genome_records, [])
        self.assertTrue(app.export_clinical_btn.disabled)

    def test_export_after_failure_writes_nothing(self):
        app = make_app()
        analyse(app)
        app._build_genome_text("garbage")
        out = self.tmpdir() / "r.md"
        export(app, out)
        self.assertFalse(out.exists())

    def test_successful_analysis_enables_export(self):
        app = make_app()
        app.export_clinical_btn.disabled = True
        analyse(app)
        self.assertFalse(app.export_clinical_btn.disabled)

    def test_export_write_error_reaches_the_user(self):
        app = make_app()
        analyse(app)
        export(app, self.tmpdir() / "missing_dir" / "r.md")
        msg, is_error = app.statuses[-1]
        self.assertTrue(is_error)
        self.assertNotIn("Saved", msg)


class LoadedPathIsTheSource(TmpMixin, unittest.TestCase):
    def big_file(self) -> Path:
        rows = "".join(f"rs{10_000_000 + i}\t3\t{1000 + i}\tAA\n" for i in range(30_000))
        body = HEADER + rows + "rs3918290\t1\t97915614\tCT\nrs429358\t19\t45411941\tCC\nrs7412\t19\t45412079\tCC\n"
        self.assertGreater(len(body), 600_000)
        p = self.tmpdir() / "big.txt"
        p.write_text(body, encoding="utf-8")
        return p

    def load(self, app, path):
        with mock.patch.object(gui, "filedialog", types.SimpleNamespace(askopenfilename=lambda **_: str(path))):
            app.load_file()

    def test_rebuild_after_load_analyses_the_whole_file(self):
        app = make_app()
        self.load(app, self.big_file())
        first = {r.rsid: r.coverage_state for r in app.genome_records}
        self.assertEqual(first["rs3918290"], "supported_and_observed")
        app.build()
        again = {r.rsid: r.coverage_state for r in app.genome_records}
        self.assertEqual(again, first)

    def test_preview_names_its_truncation(self):
        app = make_app()
        self.load(app, self.big_file())
        self.assertIn("preview", app.text.content.lower())
        self.assertIn("500,000", app.text.content)

    def test_edited_preview_is_analysed_as_new_text(self):
        app = make_app()
        self.load(app, self.big_file())
        app.text.content = SAMPLE
        app.build()
        self.assertIsNone(app.genome_path)
        self.assertEqual(app.genome_source, "")
        self.assertEqual(
            {r.rsid: r.coverage_state for r in app.genome_records}["rs3918290"], "supported_not_observed"
        )

    def test_unreadable_gz_reports_the_real_cause(self):
        p = self.tmpdir() / "bad.txt.gz"
        p.write_bytes(b"not gzip data at all")
        app = make_app()
        self.load(app, p)
        msg, is_error = app.statuses[-1]
        self.assertTrue(is_error)
        self.assertNotIn("FASTA", msg)


if __name__ == "__main__":
    unittest.main()
