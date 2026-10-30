"""Browser tests for karyogram.html (contract K-C4): reference-only load, the synthetic sample, privacy, navigation."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, REPO_ROOT, WAIT_TIMEOUT_MS, WEB_DIR, goto_ready

KARYOGRAM_SAMPLE = WEB_DIR / "demo-data" / "sample-karyogram-23andme.txt"
FIXTURES = REPO_ROOT / "tests" / "e2e" / "fixtures"
KB = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))

LOCUS_STATES = """() => Object.fromEntries(
  [...document.querySelectorAll('#karyogram-figure .kary-locus')].map((g) => [g.dataset.rsid, g.dataset.state]))"""

# Every locus's coverage state in the main app. Listed records carry theirs; the APOE component loci are not
# listed on their own, so they come from the combined APOE record's components.
APP_LOCUS_STATES = """() => {
  const s = window.__lucidase.state;
  const out = {};
  for (const r of [...s.records, ...s.negativeChecks, ...s.arrayGaps, ...s.insufficientEvidence]) {
    if (!r.components) out[r.rsid] = r.coverage_state;  // the combined APOE record is not a KB locus
  }
  if (s.apoe) for (const c of s.apoe.components) out[c.rsid] = c.coverage_state;
  return out;
}"""


def _open(page):
    page.goto(f"{page.base_url}/karyogram.html", wait_until="networkidle")
    page.wait_for_function("() => window.__lucidaseKaryogram !== undefined", timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#karyogram-figure svg")).to_be_visible()


def _data_rows(path):
    return [
        line.split("\t")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


def _total(page, name):
    return page.locator(f'#karyogram-totals [data-total="{name}"]').inner_text().strip()


def _wait_result(page):
    expect(page.locator("#karyogram-totals")).to_be_visible(timeout=WAIT_TIMEOUT_MS)


def test_load_shows_reference_only_karyogram(page):
    _open(page)
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    states = page.evaluate(LOCUS_STATES)
    assert len(states) == len(KB["loci"])
    assert set(states.values()) == {"reference"}
    expect(page.locator("#karyogram-error")).to_be_hidden()
    expect(page.locator("#karyogram-loci-body tr")).to_have_count(len(KB["genes"]))
    expect(page.locator("#karyogram-provenance")).to_contain_text("hg38")
    expect(page.locator("#karyogram-provenance")).to_contain_text(KB["manifest"]["release"])
    expect(page.locator("#karyogram-provenance")).to_contain_text("2026-10-03")
    provenance = page.locator("#karyogram-provenance")
    expect(provenance).to_contain_text("Chromosome shapes: GRCh38.")
    expect(provenance).not_to_contain_text("matching")
    expect(provenance).not_to_contain_text("doesn't say")
    expect(page.locator("#btn-load-karyogram-sample")).to_have_text("Try a made-up example file")


def test_the_page_is_the_chromosome_map_in_its_title_and_heading(page):
    _open(page)
    expect(page).to_have_title("Chromosome map · Lucidase")
    expect(page.locator("main h1")).to_have_count(1)
    expect(page.locator("main h1")).to_have_text("Chromosome map")


def test_synthetic_sample_matches_the_file_and_the_main_app(page):
    sample_rows = _data_rows(KARYOGRAM_SAMPLE)
    lengths = {n: c["length"] for n, c in KB["assemblies"]["GRCh37"]["chromosomes"].items()}
    placed = sum(1 for r in sample_rows if r[1] in lengths and 1 <= int(r[2]) <= lengths[r[1]])
    assert placed == len(sample_rows)  # the synthetic sample has nothing unplaceable

    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    expect(page.locator("#karyogram-density-notice")).to_be_hidden()
    assert _total(page, "rows") == f"{len(sample_rows):,}"
    assert _total(page, "placed") == f"{placed:,}"
    assert _total(page, "mt") == "0"
    assert _total(page, "outOfBounds") == "0"
    assert _total(page, "notPlacedBuildUnknown") == "0"
    assert _total(page, "density") == "Yes"
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    assert page.locator("#karyogram-figure .kary-bin:not(.kary-bin-empty)").count() > 0
    expect(page.locator("#karyogram-provenance")).to_contain_text("hg19")
    expect(page.locator("#karyogram-provenance")).to_contain_text("matching your file")
    expect(page.locator("#karyogram-totals")).to_contain_text("Lines read from your file")
    expect(page.locator("#karyogram-totals")).to_contain_text("Markers drawn on the map")
    karyogram_states = page.evaluate(LOCUS_STATES)
    assert "reference" not in karyogram_states.values()

    goto_ready(page, page.base_url)
    page.set_input_files("#file-input", str(KARYOGRAM_SAMPLE))
    expect(page.locator("#results-section")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    app_states = page.evaluate(APP_LOCUS_STATES)
    assert len(app_states) == len(KB["loci"])
    assert karyogram_states == app_states


def test_demo_file_loads_through_the_file_input(page):
    rows = _data_rows(DEMO_FILE)
    _open(page)
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    _wait_result(page)
    assert _total(page, "rows") == str(len(rows))
    assert _total(page, "placed") == str(len(rows))
    assert "reference" not in page.evaluate(LOCUS_STATES).values()
    expect(page.locator("#karyogram-legend")).to_contain_text("Found")


def _caption(page):
    """The line under the chromosome map that says what the map is drawn from."""
    return page.locator("figure:has(#karyogram-figure) figcaption")


def _load_named(page, name, text):
    """Chooses a file of the given name and text through the page's file input and waits for the result."""
    page.set_input_files(
        "#karyogram-file-input", files=[{"name": name, "mimeType": "text/plain", "buffer": text.encode()}]
    )
    _wait_result(page)


def test_the_figure_has_a_caption_that_names_the_reference_before_any_file(page):
    _open(page)
    expect(page.locator("figure:has(#karyogram-figure)")).to_have_count(1)
    expect(_caption(page)).to_have_text("No file yet: the chromosomes are drawn from the GRCh38 reference.")


def test_the_caption_says_made_up_example_only_for_the_built_in_sample(page):
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    expect(_caption(page)).to_have_text(
        "sample-karyogram-23andme.txt · made-up example · drawn on GRCh37 chromosome lengths."
    )


def test_a_file_named_like_the_sample_is_not_called_a_made_up_example(page):
    _open(page)
    _load_named(page, "sample-karyogram-23andme.txt", KARYOGRAM_SAMPLE.read_text(encoding="utf-8"))
    expect(_caption(page)).to_have_text("sample-karyogram-23andme.txt · drawn on GRCh37 chromosome lengths.")
    expect(_caption(page)).not_to_contain_text("made-up")


def test_a_file_that_does_not_name_its_build_is_captioned_with_the_reference_it_was_drawn_on(page):
    text = (FIXTURES / "apoe-e3e4-23andme.txt").read_text(encoding="utf-8")
    no_build = "\n".join(line for line in text.splitlines() if "build" not in line.lower()) + "\n"
    _open(page)
    _load_named(page, "no-build.txt", no_build)
    expect(_caption(page)).to_have_text(
        "no-build.txt · no genome version in the file, so the chromosomes are drawn from the GRCh38 reference."
    )


def test_a_file_that_declares_GRCh38_is_captioned_with_GRCh38(page):
    """A small synthetic file (the APOE fixture with its build header changed), never a real person's data."""
    text = (FIXTURES / "apoe-e3e4-23andme.txt").read_text(encoding="utf-8")
    assert "# build 37" in text
    _open(page)
    _load_named(page, "build-38.txt", text.replace("# build 37", "# build 38"))
    expect(_caption(page)).to_have_text("build-38.txt · drawn on GRCh38 chromosome lengths.")


def test_a_chosen_file_after_the_sample_and_a_clear_is_named_without_the_sample_label(page):
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    page.locator("#btn-karyogram-clear").click()
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    _wait_result(page)
    expect(_caption(page)).to_contain_text(DEMO_FILE.name)
    expect(_caption(page)).not_to_contain_text("made-up")


def test_clear_the_file_returns_to_the_reference_view_with_nothing_left_over(page):
    _open(page)
    expect(page.locator("#btn-karyogram-clear")).to_be_hidden()
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    clear = page.locator("#btn-karyogram-clear")
    expect(clear).to_be_visible()
    expect(clear).to_have_text("Clear the file")
    # The file pickers give way to Clear while a file is shown.
    expect(page.locator("#btn-karyogram-browse")).to_be_hidden()
    expect(page.locator("#btn-load-karyogram-sample")).to_be_hidden()
    assert "reference" not in page.evaluate(LOCUS_STATES).values()

    clear.click()
    expect(page.locator("#karyogram-main")).to_have_attribute("data-karyogram-state", "reference-only")
    expect(page.locator("#karyogram-totals")).to_be_hidden()
    expect(page.locator("#karyogram-density-notice")).to_be_hidden()
    expect(page.locator("#karyogram-error")).to_be_hidden()
    expect(page.locator("#karyogram-progress")).to_be_hidden()
    assert set(page.evaluate(LOCUS_STATES).values()) == {"reference"}
    assert page.locator("#karyogram-figure .kary-bin:not(.kary-bin-empty)").count() == 0
    rows = page.locator("#karyogram-loci-body tr")
    expect(rows).to_have_count(len(KB["genes"]))
    assert set(rows.evaluate_all("els => els.map((r) => r.dataset.state)")) == {"reference"}
    expect(page.locator("#karyogram-legend li")).to_have_count(1)
    expect(page.locator('#karyogram-legend [data-legend-count="reference"]')).to_have_text(str(len(KB["loci"])))
    expect(_caption(page)).to_have_text("No file yet: the chromosomes are drawn from the GRCh38 reference.")
    expect(page.locator("#karyogram-provenance")).to_contain_text("Chromosome shapes: GRCh38.")
    expect(page.locator("#karyogram-provenance")).not_to_contain_text("matching")
    # The file buttons are back, enabled, and focus lands on the one that starts the same job again.
    expect(clear).to_be_hidden()
    expect(page.locator("#btn-karyogram-browse")).to_be_enabled()
    expect(page.locator("#btn-load-karyogram-sample")).to_be_enabled()
    assert page.evaluate("document.activeElement.id") == "btn-karyogram-browse"

    # A second file loads cleanly after a clear, with its own caption.
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    expect(_caption(page)).to_contain_text("made-up example")
    assert "reference" not in page.evaluate(LOCUS_STATES).values()


def test_a_keyboard_load_lands_on_clear_and_clear_works_from_the_keyboard(page):
    _open(page)
    # Start the load from the keyboard: the sample button is the browse button's next Tab stop.
    page.locator("#btn-karyogram-browse").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "btn-load-karyogram-sample"
    page.keyboard.press("Enter")
    _wait_result(page)
    # The button that started the load is hidden now; focus must already be on the page's one control.
    assert page.evaluate("document.activeElement.id") == "btn-karyogram-clear"
    # Clear is a real Tab stop: step away and back by key.
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.activeElement.id") != "btn-karyogram-clear"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "btn-karyogram-clear"
    page.keyboard.press("Enter")
    expect(page.locator("#karyogram-main")).to_have_attribute("data-karyogram-state", "reference-only")
    assert page.evaluate("document.activeElement.id") == "btn-karyogram-browse"


def test_a_chosen_file_load_lands_on_clear(page):
    _open(page)
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    _wait_result(page)
    assert page.evaluate("document.activeElement.id") == "btn-karyogram-clear"


# The design system's plain result words and their one-line help (components/core/hooks.js), verbatim.
LEGEND_WORDS = {
    "supported_and_observed": ("Found", "Your file has the variant this check looks for."),
    "supported_not_observed": (
        "Not found",
        "Your file was checked here and the variant was not found among the variants tested. "
        "This is not the same as 'normal'.",
    ),
    "not_tested_by_array": ("Not on your chip", "Your DNA chip did not read this position, or the reading failed. No result."),
    "insufficient_evidence": (
        "Unclear",
        "A reading exists, but the evidence or the genotype is not clear enough to report a result.",
    ),
}


def test_without_a_file_the_key_has_one_reference_row_not_four_empty_ones(page):
    _open(page)
    items = page.locator("#karyogram-legend li")
    expect(items).to_have_count(1)
    expect(items.first).to_have_attribute("data-legend-state", "reference")
    expect(items.first.locator("[data-legend-label]")).to_have_text("Genes this report checks")
    expect(items.first.locator("[data-legend-count]")).to_have_text(str(len(KB["loci"])))
    expect(page.locator("#karyogram-legend [data-legend-help]")).to_have_count(0)
    # The same label names the reference state in each marker's hover title, not only in the key.
    marker_titles = page.locator("#karyogram-figure svg title:not(#kary-title)").evaluate_all(
        "els => els.map((e) => e.textContent)"
    )
    assert len(marker_titles) == len(KB["loci"])
    assert all(t.endswith(": Genes this report checks") for t in marker_titles), marker_titles


def test_with_a_file_the_key_has_the_four_results_whose_counts_add_up_to_the_genes(page):
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    items = page.locator("#karyogram-legend li")
    expect(items).to_have_count(4)
    assert items.evaluate_all("els => els.map((e) => e.dataset.legendState)") == list(LEGEND_WORDS)
    counts = items.locator("[data-legend-count]").evaluate_all("els => els.map((e) => Number(e.textContent))")
    assert sum(counts) == len(KB["loci"]), counts
    by_state = {}
    for state in page.evaluate(LOCUS_STATES).values():
        by_state[state] = by_state.get(state, 0) + 1
    for state, n in by_state.items():
        expect(page.locator(f'#karyogram-legend [data-legend-count="{state}"]')).to_have_text(str(n))


def test_legend_and_loci_use_the_plain_words_with_their_help(page):
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    for state, (word, help_text) in LEGEND_WORDS.items():
        item = page.locator(f'#karyogram-legend [data-legend-state="{state}"]')
        expect(item.locator("[data-legend-label]")).to_have_text(word)
        expect(item.locator("[data-legend-help]")).to_have_text(help_text)
    expect(page.locator('#karyogram-legend [data-legend-state="reference"]')).to_have_count(0)
    text = page.locator("#karyogram-legend").inner_text() + page.locator("#karyogram-loci-body").inner_text()
    titles = page.locator("#karyogram-figure").inner_html()
    for old in ("Supported", "Observed", "Array Gap", "Wild-Type", "Conflicting", "State 1", "State 2", "State 3", "State 5"):
        assert old not in text and old not in titles, old
    found = page.locator('#karyogram-loci-body tr[data-state="supported_and_observed"]').first
    expect(found.locator("td").last).to_have_text("Found")


def test_the_genes_table_has_the_design_columns_topic_gene_chromosome_your_result(page):
    _open(page)
    headers = page.locator(".lds-table thead th").all_inner_texts()
    assert [h.strip() for h in headers] == ["Topic", "Gene", "Chromosome", "Your result"]
    rows = page.locator("#karyogram-loci-body tr")
    genes = [rows.nth(i).locator("td").nth(1).inner_text().strip() for i in range(rows.count())]
    assert len(genes) == len(set(genes)) == len(KB["genes"]), f"Duplicate genes: {len(genes)} rows vs {len(set(genes))} unique"
    seen_chroms = set()
    for i in range(rows.count()):
        row = rows.nth(i)
        assert row.locator("td").count() == 4  # no Marker or Position cell, hidden or not
        gene = row.locator("td").nth(1).inner_text().strip()
        rsid = row.get_attribute("data-rsid")
        locus = KB["loci"][rsid]
        assert gene == locus["gene"], (rsid, gene)
        topic = KB["genes"][gene]["topic"]
        assert topic and topic != gene, gene  # the KB topic is a plain-words name, not the gene symbol again
        expect(row.locator("td").first).to_have_text(topic)
        # The Chromosome cell is the locus's own chromosome (the one that places its marker on the map).
        expect(row.locator("td").nth(2)).to_have_text(locus["chrom"])
        seen_chroms.add(locus["chrom"])
    assert len(seen_chroms) > 1, "the check is vacuous if every locus sits on one chromosome"
    # The rsID and the position are no longer in the table's text at all.
    table_text = page.locator(".lds-table").inner_text()
    assert not re.search(r"\brs\d+", table_text), table_text
    # The same topics and chromosomes stay on the rows after a file is read.
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    for i in range(rows.count()):
        row = rows.nth(i)
        locus = KB["loci"][row.get_attribute("data-rsid")]
        expect(row.locator("td").first).to_have_text(KB["genes"][locus["gene"]]["topic"])
        expect(row.locator("td").nth(2)).to_have_text(locus["chrom"])


def test_the_result_column_says_no_file_yet_until_a_file_gives_a_result(page):
    _open(page)
    cells = page.locator("#karyogram-loci-body tr td:last-child")
    assert cells.count() == len(KB["genes"])
    for i in range(cells.count()):
        cell = cells.nth(i)
        expect(cell).to_have_text("No file yet")
        expect(cell.locator(".lds-na-text")).to_have_count(1)
        expect(cell.locator(".kary-swatch")).to_have_count(0)  # no result mark without a result
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    for i in range(cells.count()):
        cell = cells.nth(i)
        row = page.locator("#karyogram-loci-body tr").nth(i)
        word = LEGEND_WORDS[row.get_attribute("data-state")][0]
        expect(cell).to_have_text(word)
        expect(cell.locator(".kary-swatch")).to_have_count(1)
        expect(cell.locator(".lds-na-text")).to_have_count(0)


def test_not_available_text_is_set_in_the_sans_face_not_inherited_mono(page):
    """A muted "Not available" reads in the design system's sans face even when it sits inside monospace text."""
    _open(page)
    got = page.evaluate(
        r"""() => {
          const norm = (v) => v.replace(/["'\s]/g, "");
          const host = document.createElement("code");
          host.innerHTML = '<span class="lds-na-text">Not available</span>';
          document.body.append(host);
          const family = getComputedStyle(host.firstChild).fontFamily;
          host.remove();
          return [norm(family), norm(getComputedStyle(document.documentElement).getPropertyValue("--font-sans"))];
        }"""
    )
    assert got[0] == got[1], got


def test_unknown_build_shows_the_density_notice_and_keeps_locus_states(page):
    # No existing fixture lacks a build comment, so strip it from one in memory.
    text = (FIXTURES / "apoe-e3e4-23andme.txt").read_text(encoding="utf-8")
    no_build = "\n".join(line for line in text.splitlines() if "build" not in line.lower()) + "\n"
    assert "build" not in no_build.lower()
    _open(page)
    page.set_input_files(
        "#karyogram-file-input",
        files=[{"name": "no-build.txt", "mimeType": "text/plain", "buffer": no_build.encode()}],
    )
    _wait_result(page)
    expect(page.locator("#karyogram-density-notice")).to_be_visible()
    expect(page.locator("#karyogram-density-notice")).to_contain_text("doesn't say which genome version")
    expect(page.locator("#karyogram-provenance")).to_contain_text("doesn't say which genome version it was made with")
    assert _total(page, "density") == "No"
    assert _total(page, "placed") == "0"
    assert _total(page, "notPlacedBuildUnknown") == "5"
    assert page.locator("#karyogram-figure .kary-bin:not(.kary-bin-empty)").count() == 0
    states = page.evaluate(LOCUS_STATES)
    assert states["rs429358"] == "supported_and_observed"
    assert states["rs7412"] == "supported_not_observed"
    assert states["rs6025"] == "not_tested_by_array"
    assert "reference" not in states.values()


def test_garbage_file_shows_the_error_alert(page):
    _open(page)
    page.set_input_files(
        "#karyogram-file-input",
        files=[{"name": "garbage.txt", "mimeType": "text/plain", "buffer": b"this is not\na genotype file\n"}],
    )
    expect(page.locator("#karyogram-error")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#karyogram-error")).to_contain_text("Nothing was uploaded")
    expect(page.locator("#karyogram-totals")).to_be_hidden()
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    assert set(page.evaluate(LOCUS_STATES).values()) == {"reference"}


def test_no_request_leaves_localhost_except_typekit(page):
    seen = []
    page.on("request", lambda req: seen.append(req.url))
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    external = {
        urlsplit(u).hostname
        for u in seen
        if not u.startswith(("data:", "blob:")) and urlsplit(u).hostname != "127.0.0.1"
    }
    assert external <= {"use.typekit.net"}, external


def test_navigation_links_and_theme_persist_across_pages(page):
    _open(page)
    page.locator("#btn-theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.locator("#link-analysis").click()
    page.wait_for_url("**/index.html")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.locator("#link-karyogram").click()
    page.wait_for_url("**/karyogram.html")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#karyogram-figure svg")).to_be_visible()


def test_page_works_when_storage_throws(page):
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('storage blocked'); } });"
    )
    _open(page)
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.locator("#btn-theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    _wait_result(page)


def test_a_worker_that_cannot_start_shows_the_error_and_re_enables_the_inputs(page):
    page.add_init_script("window.Worker = function () { throw new Error('worker blocked'); };")
    _open(page)
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    expect(page.locator("#karyogram-error")).to_be_visible()
    expect(page.locator("#karyogram-error-detail")).to_contain_text("worker blocked")
    expect(page.locator("#karyogram-file-input")).to_be_enabled()
    expect(page.locator("#btn-load-karyogram-sample")).to_be_enabled()
    assert page.locator("#karyogram-figure .kary-col").count() == 24


def test_file_button_and_demo_button_are_reachable_by_tab(page):
    _open(page)
    reached = []
    for _ in range(25):
        page.keyboard.press("Tab")
        ident = page.evaluate("document.activeElement && document.activeElement.id")
        if ident in ("btn-karyogram-browse", "btn-load-karyogram-sample", "karyogram-file-input"):
            reached.append(ident)
    # The button is the tab stop; the hidden native input is never focused.
    assert reached[:2] == ["btn-karyogram-browse", "btn-load-karyogram-sample"], reached
    assert "karyogram-file-input" not in reached


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_file_button_is_a_real_button_with_a_visible_focus_ring(page, theme):
    _open(page)
    if theme == "dark":
        page.locator("#btn-theme-toggle").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    button = page.locator("#btn-karyogram-browse")
    expect(button).to_have_text("Choose your DNA file")
    expect(page.locator("#karyogram-file-input")).to_be_hidden()
    assert button.bounding_box()["height"] >= 40
    # Reach it the way a keyboard user does: Tab from the page start until it is focused.
    for _ in range(25):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "btn-karyogram-browse":
            break
    else:
        pytest.fail("the file button was never reached by Tab")
    _assert_focus_ring(page)
    # The sample button is the next tab stop and carries the same ring.
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "btn-load-karyogram-sample"
    _assert_focus_ring(page)


def _assert_focus_ring(page):
    ring = page.evaluate(
        """() => {
          const cs = getComputedStyle(document.activeElement);
          const probe = document.createElement('i');
          probe.style.color = getComputedStyle(document.documentElement).getPropertyValue('--accent');
          document.body.appendChild(probe);
          const accent = getComputedStyle(probe).color;
          probe.remove();
          return { style: cs.outlineStyle, width: cs.outlineWidth, offset: cs.outlineOffset,
                   color: cs.outlineColor, accent };
        }"""
    )
    assert ring["style"] == "solid" and ring["width"] == "2px", ring
    assert ring["offset"] == "2px", ring
    assert ring["color"] == ring["accent"], ring


def test_file_button_opens_the_picker(page):
    _open(page)
    with page.expect_file_chooser() as chooser:
        page.locator("#btn-karyogram-browse").click()
    chooser.value.set_files(str(DEMO_FILE))
    _wait_result(page)


@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_file_button_opens_the_picker_from_the_keyboard(page, key):
    _open(page)
    button = page.locator("#btn-karyogram-browse")
    button.focus()
    expect(button).to_be_focused()
    with page.expect_file_chooser() as chooser:
        button.press(key)
    chooser.value.set_files(str(DEMO_FILE))
    _wait_result(page)


def test_or_stays_with_the_sample_button_when_the_row_wraps(page):
    page.set_viewport_size({"width": 390, "height": 800})
    _open(page)
    or_box = page.locator("#btn-load-karyogram-sample").locator("xpath=preceding-sibling::span").bounding_box()
    sample = page.locator("#btn-load-karyogram-sample").bounding_box()
    browse = page.locator("#btn-karyogram-browse").bounding_box()
    # The row did wrap (the sample button sits below the file button) and "or" shares its line.
    assert sample["y"] >= browse["y"] + browse["height"] - 1, (browse, sample)
    assert or_box["y"] < sample["y"] + sample["height"] and sample["y"] < or_box["y"] + or_box["height"], (or_box, sample)


def test_index_header_links_to_the_karyogram_page(page):
    goto_ready(page, page.base_url)
    assert page.locator("#link-karyogram").get_attribute("href") == "karyogram.html"


def test_the_page_has_no_inline_script():
    html = (WEB_DIR / "karyogram.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.S)
    assert scripts and all(s.strip() == "" for s in scripts)
    assert 'type="module" src="src/karyogram-page.js"' in html


def test_karyogram_page_loads_the_owners_font_kit_like_the_main_page():
    html = (WEB_DIR / "karyogram.html").read_text(encoding="utf-8")
    index = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    link = '<link rel="stylesheet" href="https://use.typekit.net/gfe3vcu.css" id="typekit-stylesheet">'
    assert link in html and link in index
    assert html.count("use.typekit.net") == 1  # no second kit


@pytest.mark.allow_console_errors
def test_transient_worker_module_failure_is_retried_once(page):
    # Same rule as the main page: a worker whose module graph fails to load raises a message-less error event.
    # That is a transient start failure, so the page starts one fresh worker with the same job.
    aborted = []

    def flaky(route):
        if aborted:
            route.continue_()
        else:
            aborted.append(route.request.url)
            route.abort("connectionreset")

    _open(page)
    page.route("**/src/core/classify.js", flaky)
    page.locator("#btn-load-karyogram-sample").click()
    expect(page.locator("#karyogram-totals")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#karyogram-error")).to_be_hidden()
    assert len(aborted) == 1


COUNT_WORKERS = """(() => {
  const Real = window.Worker;
  window.__workerCount = 0;
  window.Worker = class extends Real {
    constructor(...args) {
      super(...args);
      window.__workerCount += 1;
    }
  };
})();"""


@pytest.mark.allow_console_errors
def test_persistent_worker_module_failure_shows_the_error_and_frees_the_inputs(page):
    page.add_init_script(COUNT_WORKERS)
    _open(page)
    page.route("**/src/core/classify.js", lambda route: route.abort("connectionreset"))
    page.locator("#btn-load-karyogram-sample").click()
    expect(page.locator("#karyogram-error")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#karyogram-totals")).to_be_hidden()
    expect(page.locator("#karyogram-file-input")).to_be_enabled()
    expect(page.locator("#btn-load-karyogram-sample")).to_be_enabled()
    # Exactly one retry: the first worker plus one fresh one, never a third and never just one.
    assert page.evaluate("window.__workerCount") == 2


def test_a_worker_that_cannot_start_shows_the_error_from_the_demo_button(page):
    # The demo button reaches startWorker through loadSample's try/catch rather than the FileReader callback.
    page.add_init_script("window.Worker = function () { throw new Error('worker blocked'); };")
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    expect(page.locator("#karyogram-error")).to_be_visible()
    expect(page.locator("#karyogram-error-detail")).to_contain_text("worker blocked")
    expect(page.locator("#karyogram-file-input")).to_be_enabled()
    expect(page.locator("#btn-load-karyogram-sample")).to_be_enabled()
    assert page.locator("#karyogram-figure .kary-col").count() == 24


# The page cannot be handed an unknown state through its public surface, so the worker's answer is tampered with:
# the real worker runs, and its layout reaches the page with one observation set to a state the page does not know.
TAMPER_OBSERVATION = """(() => {
  const Real = window.Worker;
  window.Worker = class extends Real {
    set onmessage(fn) {
      super.onmessage = (e) => {
        const obs = e.data && e.data.layout && e.data.layout.sample && e.data.layout.sample.observations;
        if (obs) obs[Object.keys(obs)[0]] = 'bogus_state';
        fn(e);
      };
    }
  };
})();"""


def test_an_unknown_locus_state_fails_fast_to_the_error_alert(page):
    page.add_init_script(TAMPER_OBSERVATION)
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    expect(page.locator("#karyogram-error")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#karyogram-error-detail")).to_contain_text("bogus_state")
    expect(page.locator("#karyogram-totals")).to_be_hidden()
    expect(page.locator("#karyogram-file-input")).to_be_enabled()
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    assert set(page.evaluate(LOCUS_STATES).values()) == {"reference"}


def _assert_failed_and_inputs_free(page):
    expect(page.locator("#karyogram-error")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#karyogram-totals")).to_be_hidden()
    expect(page.locator("#karyogram-file-input")).to_be_enabled()
    expect(page.locator("#btn-load-karyogram-sample")).to_be_enabled()
    assert page.locator("#karyogram-figure .kary-col").count() == 24


# The page sets onmessageerror right after construction, so the handler is called on the next task.
# It is called directly because in Chromium a synthetic dispatchEvent(new MessageEvent("messageerror"))
# on a real Worker does not reach onmessageerror. The test therefore relies on the page assigning
# the onmessageerror property (not addEventListener).
MESSAGE_ERROR = """(() => {
  const Real = window.Worker;
  window.Worker = class extends Real {
    constructor(...args) {
      super(...args);
      setTimeout(() => this.onmessageerror(new MessageEvent("messageerror")), 0);
    }
  };
})();"""


def test_a_worker_message_error_shows_the_error_and_frees_the_inputs(page):
    page.add_init_script(MESSAGE_ERROR)
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _assert_failed_and_inputs_free(page)
    expect(page.locator("#karyogram-error-detail")).to_contain_text("could not read")


def test_a_file_reader_failure_shows_the_error_and_frees_the_inputs(page):
    page.add_init_script(
        "FileReader.prototype.readAsText = function () {"
        " setTimeout(() => this.onerror && this.onerror(new ProgressEvent('error')), 0); };"
    )
    _open(page)
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    _assert_failed_and_inputs_free(page)
    expect(page.locator("#karyogram-error-detail")).to_contain_text("Failed to read file from disk")


def test_a_silent_worker_trips_the_watchdog(page):
    # A worker that never answers: the 30 s watchdog is fast-forwarded with the fake clock, not waited for.
    # The watchdog is armed only once the sample has been fetched and the job posted, so the fetch is held
    # back until the test has seen the clock run, and the clock runs only after the silent worker got its job.
    held = []
    page.route("**/sample-karyogram-23andme.txt", lambda route: held.append(route))
    page.add_init_script(
        "window.Worker = class {"
        " postMessage() { window.__jobPosted = true; } terminate() {} };"
    )
    page.clock.install()
    _open(page)
    with page.expect_request("**/sample-karyogram-23andme.txt"):
        page.locator("#btn-load-karyogram-sample").click()
    expect(page.locator("#karyogram-progress")).to_be_visible()
    assert page.evaluate("() => window.__jobPosted") is None, "no watchdog can exist before the fetch ends"
    assert len(held) == 1, "the sample request should be held by the route"
    held[0].continue_()
    page.wait_for_function("() => window.__jobPosted === true", timeout=WAIT_TIMEOUT_MS)
    page.clock.run_for(31000)
    _assert_failed_and_inputs_free(page)
    expect(page.locator("#karyogram-error-detail")).to_contain_text("stopped responding")


@pytest.mark.allow_console_errors
def test_a_sample_fetch_that_never_answers_times_out_to_the_error_and_can_be_retried(page):
    # The first sample request is held; the fake clock runs past the 30 s budget instead of waiting it out.
    # Later requests (the retry) go through.
    held = []

    def hold_first(route):
        if held:
            route.continue_()
        else:
            held.append(route)

    page.route("**/sample-karyogram-23andme.txt", hold_first)
    page.add_init_script(COUNT_WORKERS)
    page.clock.install()
    _open(page)
    with page.expect_request("**/sample-karyogram-23andme.txt"):
        page.locator("#btn-load-karyogram-sample").click()
    expect(page.locator("#karyogram-progress")).to_be_visible()
    expect(page.locator("#karyogram-main")).to_have_attribute("data-karyogram-state", "loading")
    assert len(held) == 1, "the sample request should be held by the route"
    page.clock.run_for(31000)
    _assert_failed_and_inputs_free(page)
    expect(page.locator("#karyogram-error-detail")).to_contain_text("did not load in time")
    expect(page.locator("#karyogram-progress")).to_be_hidden()
    expect(page.locator("#karyogram-main")).to_have_attribute("data-karyogram-state", "error")

    # The held response arrives late: it must not start a job or replace the error.
    with page.expect_response("**/sample-karyogram-23andme.txt"):
        held[0].continue_()
    page.wait_for_timeout(500)
    expect(page.locator("#karyogram-error")).to_be_visible()
    expect(page.locator("#karyogram-main")).to_have_attribute("data-karyogram-state", "error")
    assert page.evaluate("window.__workerCount") == 0

    # Trying again works.
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    expect(page.locator("#karyogram-error")).to_be_hidden()
    expect(page.locator("#karyogram-main")).to_have_attribute("data-karyogram-state", "result")


# The computed shape of one mark: everything that distinguishes the marks except colour.
MARK_SHAPES = """(selector) => {
  const out = {};
  for (const el of document.querySelectorAll(selector)) {
    const s = getComputedStyle(el);
    const state = [...el.classList, ...el.parentElement.classList].find((c) => c.startsWith('kary-state-'));
    const hollow = el.tagName === 'circle' ? s.fill !== s.stroke : s.backgroundColor === 'rgba(0, 0, 0, 0)';
    out[state] = [hollow, s.clipPath, s.strokeDasharray, s.backgroundImage, s.borderTopStyle].join('|');
  }
  return out;
}"""


def test_each_result_on_the_map_has_its_own_mark_not_only_a_colour(page):
    _open(page)
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)
    swatches = page.evaluate(MARK_SHAPES, "#karyogram-legend .kary-swatch")
    assert "kary-state-reference" not in swatches  # shown only before a file is loaded, never beside the results
    assert len(set(swatches.values())) == len(swatches), swatches
    cores = page.evaluate(MARK_SHAPES, "#karyogram-figure .kary-locus .kary-core")
    assert "kary-state-insufficient_evidence" in cores, cores  # the sample has an unclear result to check
    assert len(set(cores.values())) == len(cores), cores


def test_on_a_phone_the_figure_keeps_its_drawn_size_and_scrolls_inside_a_named_region(page):
    page.set_viewport_size({"width": 390, "height": 800})
    _open(page)
    figure = page.locator("#karyogram-figure")
    expect(figure).to_have_attribute("role", "region")
    expect(figure).to_have_attribute("aria-label", "Chromosome map")
    expect(figure).to_have_attribute("tabindex", "0")
    assert figure.evaluate("el => getComputedStyle(el).overflowX") == "auto"
    dims = figure.evaluate("el => ({ scroll: el.scrollWidth, client: el.clientWidth })")
    assert dims["scroll"] > dims["client"], dims

    # Rendered sizes: the SVG's scale times each label's font size, and each mark's halo as drawn.
    svg = figure.locator("svg")
    scale = svg.evaluate("svg => svg.getBoundingClientRect().width / svg.viewBox.baseVal.width")
    assert scale >= 1, scale
    sizes = figure.locator(".kary-label").evaluate_all("els => els.map((t) => parseFloat(getComputedStyle(t).fontSize))")
    assert len(sizes) == 24 and min(sizes) * scale >= 11, (sizes, scale)
    rendered = figure.locator(".kary-label").evaluate_all(
        "els => els.map((t) => t.getBoundingClientRect().height)"
    )
    assert min(rendered) >= 11 * 0.7, rendered  # glyph boxes really are drawn at that size, not shrunk by a transform
    halos = figure.locator(".kary-locus .kary-halo").evaluate_all("els => els.map((c) => c.getBoundingClientRect().width)")
    assert len(halos) == len(KB["loci"]) and min(halos) >= 20, halos

    # The region takes focus and scrolls from the keyboard; the page itself never scrolls sideways.
    figure.focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_function("() => document.getElementById('karyogram-figure').scrollLeft > 0")
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0, f"the page scrolls sideways by {overflow}px"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_figure_region_shows_the_accent_focus_ring_from_the_keyboard(page, theme):
    page.set_viewport_size({"width": 390, "height": 800})
    _open(page)
    if theme == "dark":
        page.locator("#btn-theme-toggle").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "karyogram-figure":
            break
    else:
        pytest.fail("the figure region was never reached by Tab")
    _assert_focus_ring(page)


def test_on_a_desktop_the_figure_needs_no_scrolling(page):
    _open(page)
    dims = page.locator("#karyogram-figure").evaluate("el => ({ scroll: el.scrollWidth, client: el.clientWidth })")
    assert dims["scroll"] <= dims["client"], dims


# The scroll box may overflow by a few pixels (fallback fonts differ by platform); this bounds how many.
PHONE_TABLE_MAX_OVERFLOW_PX = 48


def _assert_genes_table_never_clips(page):
    """Assert the phone-width genes table scrolls inside its box at worst, and never clips the result word.

    The design's answer to a table slightly wider than the screen is the wrapper's own ``overflow-x: auto``
    scroll, so a few pixels of in-box scroll are accepted; clipping is the only defect. Five checks: the
    wrapper is a real scroller, whatever overflows is small, every cell lies inside the scrollable extent,
    each result cell holds its whole word, and the result column can be scrolled fully into view.
    """
    wrapper = page.locator("#karyogram-loci-body").locator("xpath=ancestor::div[contains(@class,'lds-section-body')][1]")
    box = wrapper.bounding_box()
    assert wrapper.evaluate("el => getComputedStyle(el).overflowX") == "auto", "the wrapper is not a scroller"
    dims = wrapper.evaluate("el => ({ scroll: el.scrollWidth, client: el.clientWidth })")
    # Regression canary: a returned column or grown padding would add far more than this bound.
    assert dims["scroll"] - dims["client"] <= PHONE_TABLE_MAX_OVERFLOW_PX, f"the overflow is too large: {dims}"
    rects = page.locator("#karyogram-loci-body td, .lds-table thead th").evaluate_all(
        "els => els.map((c) => { const r = c.getBoundingClientRect(); return [r.left, r.right]; })"
    )
    assert len(rects) == len(KB["genes"]) * 4 + 4
    for left, right in rects:
        assert left >= box["x"] - 0.5 and right <= box["x"] + dims["scroll"] + 0.5, (
            f"a cell lies outside the scrollable extent: {(left, right, box, dims)}"
        )
    # The result cell shows its whole word: the text is not wider than the cell that holds it.
    words = page.locator("#karyogram-loci-body tr td:last-child").evaluate_all(
        "els => els.map((c) => c.scrollWidth - c.clientWidth)"
    )
    assert max(words) <= 0, f"a result word is cut off in its cell: {words}"
    # The result column can be brought fully into view by scrolling the wrapper to its end.
    wrapper.evaluate("el => { el.scrollLeft = el.scrollWidth; }")
    ends = page.locator("#karyogram-loci-body tr td:last-child").evaluate_all(
        "els => els.map((c) => { const r = c.getBoundingClientRect(); return [r.left, r.right]; })"
    )
    for left, right in ends:
        assert left >= box["x"] - 0.5 and right <= box["x"] + box["width"] + 0.5, (
            f"the result word cannot be scrolled into view: {(left, right, box)}"
        )


@pytest.mark.parametrize("loaded", [False, True])
def test_on_a_phone_the_genes_table_never_clips_the_result_word(page, loaded):
    page.set_viewport_size({"width": 390, "height": 800})
    _open(page)
    if loaded:
        page.locator("#btn-load-karyogram-sample").click()
        _wait_result(page)
    _assert_genes_table_never_clips(page)


def test_karyogram_jpeg_export_downloads_high_res_jpeg_on_theme_background(page, tmp_path):
    _open(page)
    btn_export = page.locator("#btn-karyogram-export")
    expect(btn_export).to_be_visible()
    expect(btn_export).to_be_enabled()

    # 1. Export reference karyogram
    with page.expect_download() as download_info:
        btn_export.click()
    download = download_info.value
    assert download.suggested_filename == "Lucidase_Chromosome_Map.jpg"
    ref_path = tmp_path / "ref_map.jpg"
    download.save_as(ref_path)
    assert ref_path.stat().st_size > 20000

    # 2. Toggle to dark theme, load sample, and export
    page.locator("#btn-theme-toggle").click()
    page.locator("#btn-load-karyogram-sample").click()
    _wait_result(page)

    with page.expect_download() as download_info:
        btn_export.click()
    download_sample = download_info.value
    assert "Lucidase_Chromosome_Map" in download_sample.suggested_filename
    assert download_sample.suggested_filename.endswith(".jpg")
    sample_path = tmp_path / "sample_map.jpg"
    download_sample.save_as(sample_path)
    assert sample_path.stat().st_size > 50000

    # Verify resolution and JPEG validity with PIL
    from PIL import Image
    with Image.open(sample_path) as img:
        assert img.format == "JPEG"
        assert img.width >= 1400
        assert img.height >= 1000
        # Dark theme background corner check
        corner = img.getpixel((5, 5))
        assert corner[0] < 30 and corner[1] < 30 and corner[2] < 35

