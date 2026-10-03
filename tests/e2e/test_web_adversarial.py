"""Adversarial and interaction tests for the web dashboard (converted from the
former uncollected tests/test_web_adversarial.py script).

Dropped on conversion because they encoded behaviour listed as wrong in
findings.md: the hard-coded "ClinVar 2024-06" badge text (stale KB metadata,
replaced by the KB manifest in later tasks), the exact empty-file result
("0 SNPs / 0.00%", where an empty file should be rejected, T3), and the
APOE-in-Carrier-filter check (P0-007: category-derived classification), and
the multi-locus assortment section / "Mendel's 2nd law" card text (P1-026: the
F5+F2 comparison is itself wrong, T8 rewrites it). Also not carried over: the
printed-only pathogenic count and drawer phenotype text, which asserted nothing.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect

from conftest import wait_drawer_closed, wait_drawer_open

FIXTURES = Path(__file__).parent / "fixtures"
EVIL_QUERIES = [
    "(a+)+$",
    "[*+?^${}()|[\\]]",
    "<script>alert(1)</script>",
    "../../../../etc/passwd",
    "'; DROP TABLE variants; --",
    "\U0001f9ec\U0001f52c⚡✨\U0001f4a5",
    "A" * 500,
]


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()


def _wait_outcome(page):
    """Wait until the run ends in either results or a visible analysis error."""
    page.wait_for_function(
        "() => ['results-section', 'analysis-error'].some("
        "id => document.getElementById(id).getBoundingClientRect().height > 0)",
    )


def test_page_title(loaded_page):
    assert "Lucidase" in loaded_page.title()


def test_demo_qc_numbers_present(loaded_page):
    _load_demo(loaded_page)
    total = loaded_page.locator("#qc-total-snps").text_content()
    assert int(total.replace(",", "")) >= 20


def test_search_survives_adversarial_queries(loaded_page):
    _load_demo(loaded_page)
    search = loaded_page.locator("#search-input")
    for query in EVIL_QUERIES:
        search.fill(query)
        assert "Showing" in loaded_page.locator("#showing-count").text_content(), query
    search.fill("")


def test_drawer_opens_and_closes(loaded_page):
    _load_demo(loaded_page)
    loaded_page.locator("#variants-tbody tr").first.click()
    wait_drawer_open(loaded_page)
    assert loaded_page.locator("#drawer-rsid").text_content().strip()
    assert loaded_page.locator("#drawer-gene").text_content().strip()
    loaded_page.locator("#btn-close-drawer").click()
    wait_drawer_closed(loaded_page)


def test_drawer_screenshot_to_tmp(loaded_page, tmp_path):
    _load_demo(loaded_page)
    loaded_page.locator("#variants-tbody tr").first.click()
    wait_drawer_open(loaded_page)
    shot = tmp_path / "drawer.png"
    loaded_page.screenshot(path=str(shot), full_page=True)
    assert shot.stat().st_size > 0


def test_filter_transitions(loaded_page):
    _load_demo(loaded_page)
    for name in ["pathogenic", "acmg", "pgx", "carrier", "risk", "all"]:
        loaded_page.locator(f"[data-filter='{name}']").click()
        assert "Showing" in loaded_page.locator("#showing-count").text_content(), name


# What each filter shows today. The Risk Factors filter keeps APOE through its e3/e4 and e4/e4 diplotype rule (S2-F6
# owns that rule); the rest follow the KB category. The wild-type fixture has no observed variant, so every filter
# is empty for it.
DEMO_FILTER_ROWS = {
    "all": {
        "APOE (rs429358 + rs7412)", "rs3918290", "rs6025", "rs1799963", "rs4149056", "rs4244285",
        "rs113993960", "rs9923231", "rs1800562", "rs4988235", "rs1799945", "rs1801133",
    },
    "pathogenic": set(),
    "carrier": {"rs113993960", "rs1800562", "rs1799945"},
    "pgx": {"rs3918290", "rs4149056", "rs4244285", "rs9923231"},
    "risk": {"APOE (rs429358 + rs7412)", "rs6025", "rs1799963"},
}


def _shown_ids(page):
    """The first-cell ids of the rows the table shows now (an empty filter shows no data row)."""
    return set(
        page.evaluate(
            "() => [...document.querySelectorAll('#variants-tbody tr')]"
            ".filter(r => r.children.length > 1).map(r => r.children[0].textContent.trim())"
        )
    )


def _filter_sets(page):
    shown = {}
    for name in DEMO_FILTER_ROWS:
        page.locator(f"[data-filter='{name}']").click()
        shown[name] = _shown_ids(page)
    return shown


def test_each_filter_shows_the_exact_demo_rows(loaded_page):
    _load_demo(loaded_page)
    assert _filter_sets(loaded_page) == DEMO_FILTER_ROWS


def test_each_filter_is_empty_for_the_wild_type_file(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "wildtype-23andme.txt"))
    expect(loaded_page.locator("#results-section")).to_be_visible()
    assert _filter_sets(loaded_page) == {name: set() for name in DEMO_FILTER_ROWS}


def test_kb_provenance_badge_visible(loaded_page):
    _load_demo(loaded_page)
    badge = loaded_page.locator("#kb-provenance-badge")
    expect(badge).to_be_visible()
    assert badge.text_content().strip()


def test_xss_payloads_in_rsids_do_not_execute(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "xss-23andme.txt"))
    # A valid 23andMe file: results must render, an error would be a failure here.
    expect(loaded_page.locator("#results-section")).to_be_visible()
    executed = loaded_page.evaluate(
        "() => Boolean(window.__xss_rsid || window.__xss_img || window.__xss_gt)"
    )
    assert not executed, "XSS payload executed in the page context"


def test_empty_file_is_rejected_without_nan(loaded_page):
    loaded_page.set_input_files(
        "#file-input", files=[{"name": "empty.txt", "mimeType": "text/plain", "buffer": b""}]
    )
    _wait_outcome(loaded_page)
    alert = loaded_page.locator("#analysis-error")
    expect(alert).to_be_visible()
    assert loaded_page.locator("#analysis-error-detail").inner_text().strip() != ""
    expect(loaded_page.locator("#results-section")).to_be_hidden()
    shown = loaded_page.locator("#qc-call-rate").text_content()
    assert "NaN" not in shown and "Infinity" not in shown


def test_corrupt_binary_garbage_is_survived(loaded_page):
    garbage = (
        "\x00\x01\x02\xff\xfe\r\nNOT_A_GENOME_LINE\r\n"
        + "#" * 5000
        + "\r\n"
        + "A" * 100000
        + "\r\nrs429358\t19\t-99999\tCC\r\nrs1800562\t\t\t\r\nCORRUPT\t1\tNaN\t??\r\n"
    )
    loaded_page.set_input_files(
        "#file-input",
        files=[{"name": "corrupt.bin", "mimeType": "text/plain", "buffer": garbage.encode("utf-8")}],
    )
    _wait_outcome(loaded_page)
    # Contracts C1: unrecognised content is rejected, never guessed at.
    alert = loaded_page.locator("#analysis-error")
    expect(alert).to_be_visible()
    assert "unsupported" in alert.inner_text().lower()
    expect(loaded_page.locator("#results-section")).to_be_hidden()


def test_export_handlers_run(loaded_page):
    _load_demo(loaded_page)
    loaded_page.evaluate("window.__lucidase.exportMarkdownReport()")
    loaded_page.evaluate("window.__lucidase.exportCsvReport()")


def test_apoe_e3e4_upload_and_inspect(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "apoe-e3e4-23andme.txt"))
    loaded_page.locator("#apoe-status-card").wait_for(state="visible")
    assert "ε3/ε4" in loaded_page.locator("#apoe-diplotype-title").text_content()
    assert "3–4×" in loaded_page.locator("#apoe-risk-ratio").text_content()
    loaded_page.locator("#btn-inspect-apoe").click()
    wait_drawer_open(loaded_page)
    assert loaded_page.locator("#drawer-gene").text_content() == "APOE"


def test_typekit_stylesheet_linked(loaded_page):
    assert loaded_page.locator("link[href*='use.typekit.net/gfe3vcu.css']").count() == 1


def test_theme_toggle_round_trip(loaded_page):
    page = loaded_page
    theme = "document.documentElement.getAttribute('data-theme')"
    assert page.evaluate(theme) == "light"
    page.locator("#btn-theme-toggle").click()
    assert page.evaluate(theme) == "dark"
    page.locator("#btn-theme-toggle").click()
    assert page.evaluate(theme) == "light"
