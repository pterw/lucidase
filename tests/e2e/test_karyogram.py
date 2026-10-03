"""Browser tests for karyogram.html (contract K-C4): reference-only load, the synthetic sample, privacy, navigation."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from playwright.sync_api import expect

from conftest import DEMO_FILE, REPO_ROOT, WEB_DIR

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
    expect(page.locator("#karyogram-totals")).to_be_visible(timeout=30000)


def test_load_shows_reference_only_karyogram(page):
    _open(page)
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    states = page.evaluate(LOCUS_STATES)
    assert len(states) == 14
    assert set(states.values()) == {"reference"}
    expect(page.locator("#karyogram-error")).to_be_hidden()
    expect(page.locator("#karyogram-loci-body tr")).to_have_count(14)
    expect(page.locator("#karyogram-provenance")).to_contain_text("hg38")
    expect(page.locator("#karyogram-provenance")).to_contain_text(KB["manifest"]["release"])
    expect(page.locator("#karyogram-provenance")).to_contain_text("2026-10-03")


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
    assert _total(page, "density") == "Available"
    assert page.locator("#karyogram-figure .kary-col").count() == 24
    assert page.locator("#karyogram-figure .kary-bin:not(.kary-bin-empty)").count() > 0
    expect(page.locator("#karyogram-provenance")).to_contain_text("hg19")
    karyogram_states = page.evaluate(LOCUS_STATES)
    assert "reference" not in karyogram_states.values()

    page.goto(page.base_url, wait_until="networkidle")
    page.set_input_files("#file-input", str(KARYOGRAM_SAMPLE))
    expect(page.locator("#results-section")).to_be_visible(timeout=30000)
    app_states = page.evaluate(APP_LOCUS_STATES)
    assert len(app_states) == 14
    assert karyogram_states == app_states


def test_demo_file_loads_through_the_file_input(page):
    rows = _data_rows(DEMO_FILE)
    _open(page)
    page.set_input_files("#karyogram-file-input", str(DEMO_FILE))
    _wait_result(page)
    assert _total(page, "rows") == str(len(rows))
    assert _total(page, "placed") == str(len(rows))
    assert "reference" not in page.evaluate(LOCUS_STATES).values()
    expect(page.locator("#karyogram-legend")).to_contain_text("Supported & Observed")


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
    expect(page.locator("#karyogram-density-notice")).to_contain_text("genome build is unknown")
    assert _total(page, "density") == "Unavailable"
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
    expect(page.locator("#karyogram-error")).to_be_visible(timeout=15000)
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


def test_file_input_and_demo_button_are_reachable_by_tab(page):
    _open(page)
    reached = []
    for _ in range(25):
        page.keyboard.press("Tab")
        ident = page.evaluate("document.activeElement && document.activeElement.id")
        if ident in ("karyogram-file-input", "btn-load-karyogram-sample"):
            reached.append(ident)
    assert reached[:2] == ["karyogram-file-input", "btn-load-karyogram-sample"], reached


def test_index_header_links_to_the_karyogram_page(page):
    page.goto(page.base_url, wait_until="networkidle")
    assert page.locator("#link-karyogram").get_attribute("href") == "karyogram.html"


def test_the_page_has_no_inline_script():
    html = (WEB_DIR / "karyogram.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.S)
    assert scripts and all(s.strip() == "" for s in scripts)
    assert 'type="module" src="src/karyogram-page.js"' in html
