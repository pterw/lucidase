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

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, apoe_row, open_apoe, show_table, wait_drawer_closed, wait_drawer_open

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
    show_table(page)


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
    for name in ["pathogenic", "acmg", "pgx", "carrier", "risk", "observed", "every"]:
        loaded_page.locator(f"[data-filter='{name}']").click()
        assert "Showing" in loaded_page.locator("#showing-count").text_content(), name


# What each filter shows today. "observed" is the Found tab and the category filters narrow it: the demo's HFE H63D
# (rs1799945) and MTHFR (rs1801133) are variant readings with unclear evidence, so they are under Unclear, not here.
# The Risk Factors filter keeps APOE through its e3/e4 and e4/e4 diplotype rule (S2-F6 owns that rule); the rest
# follow the KB category. The wild-type fixture has no found variant, so every filter is empty for it.
DEMO_FILTER_ROWS = {
    "observed": {
        "APOE (rs429358 + rs7412)", "rs3918290", "rs6025", "rs1799963", "rs4149056", "rs4244285",
        "rs113993960", "rs9923231", "rs1800562", "rs4988235",
    },
    "pathogenic": set(),
    "carrier": {"rs113993960", "rs1800562"},
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
    show_table(page)
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


# The tabs named by a result word: (tab, state key, plain word, the summary strip's count element).
STATE_TABS = [
    ("observed", "supported_and_observed", "Found", "count-state-observed"),
    ("negative", "supported_not_observed", "Not found", "count-state-negative"),
    ("gaps", "not_tested_by_array", "Not on your chip", "count-state-gaps"),
    ("insufficient", "insufficient_evidence", "Unclear", "count-state-insufficient"),
]
CATEGORY_TABS = ("pathogenic", "carrier", "pgx", "risk", "acmg")


def _shown_rows(page):
    """(id, result word, gene) of each data row the table shows now."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#variants-tbody tr')].filter(r => r.children.length > 1)"
        ".map(r => [r.children[0].textContent.trim(), r.children[3].textContent.trim(),"
        " r.children[1].querySelector('.font-bold').textContent.trim()])"
    )


def _ids_by_state(page):
    """Each check's id under its own coverage state, from the worker's (overlapping) lists."""
    return page.evaluate(
        "() => { const s = window.__lucidase.state; const out = {};"
        " for (const vm of [...s.records, ...s.negativeChecks, ...s.arrayGaps, ...s.insufficientEvidence])"
        " (out[vm.coverage_state] ??= new Set()).add(vm.id);"
        " return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, [...v]])); }"
    )


def _count(page, element_id):
    return int(page.locator(f"#{element_id}").text_content().replace(",", ""))


# Demo: 10 Found, 1 Not found, 2 Unclear (H63D and MTHFR: variant present, evidence unclear; the worker also lists
# them with the variant-present findings). Wild type: 9 Not found, 2 Not on your chip, 2 Unclear (H63D and MTHFR
# wild type; the worker also lists them with the wild-type checks). Between them every state tab is non-empty once.
STATE_TAB_COUNTS = {
    "demo": {"observed": 10, "negative": 1, "gaps": 0, "insufficient": 2},
    "wildtype": {"observed": 0, "negative": 9, "gaps": 2, "insufficient": 2},
}


@pytest.mark.parametrize("sample", ["demo", "wildtype"])
def test_each_state_tab_lists_exactly_the_checks_with_its_word_and_agrees_with_the_summary(loaded_page, sample):
    page = loaded_page
    page.set_input_files("#file-input", str(DEMO_FILE if sample == "demo" else FIXTURES / "wildtype-23andme.txt"))
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)
    by_state = _ids_by_state(page)
    for tab, state, word, count_id in STATE_TABS:
        page.locator(f"[data-filter='{tab}']").click()
        rows = _shown_rows(page)
        ids = [row[0] for row in rows]
        assert [row[1] for row in rows] == [word] * len(rows), f"{tab}: {rows}"
        assert sorted(ids) == sorted(by_state.get(state, [])), f"{tab}: {ids}"
        assert len(set(ids)) == len(ids), f"{tab} repeats a check: {ids}"
        assert len(rows) == STATE_TAB_COUNTS[sample][tab], f"{tab}: {ids}"
        assert _count(page, count_id) == len(rows), f"{tab}: the summary strip says {_count(page, count_id)}"
        assert page.locator("#showing-count").text_content().startswith(f"Showing {len(rows)} "), tab
    if sample == "demo":
        page.locator("[data-filter='insufficient']").click()
        assert {row[0] for row in _shown_rows(page)} == {"rs1799945", "rs1801133"}


def test_each_category_tab_narrows_the_found_checks_and_agrees_with_the_report_groups(loaded_page):
    page = loaded_page
    _load_demo(page)
    page.locator("[data-filter='observed']").click()
    found = {row[0] for row in _shown_rows(page)}
    assert len(found) == _count(page, "count-state-observed") == 10
    # The report groups hold the same Found checks, one row each.
    assert page.locator("#report-groups article.lds-finding:has(> span.lds-mark-supported_and_observed)").count() == 10
    shown_any = False
    for tab in CATEGORY_TABS:
        page.locator(f"[data-filter='{tab}']").click()
        rows = _shown_rows(page)
        shown_any = shown_any or bool(rows)
        assert {row[1] for row in rows} <= {"Found"}, f"{tab}: {rows}"
        assert {row[0] for row in rows} <= found, f"{tab}: {rows}"
        # The report groups list each of those checks as a Found row.
        for row in rows:
            report_row = page.locator(f'#report-groups article.lds-finding[data-finding-id="{row[0]}"]')
            expect(report_row.locator(":scope > span.lds-mark-supported_and_observed")).to_have_count(1)
        assert page.locator("#showing-count").text_content() == f"Showing {len(rows)} of {len(found)} findings", tab
    assert shown_any, "no category tab showed a row, so this test proved nothing"


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
    apoe_row(loaded_page).wait_for(state="visible")
    open_apoe(loaded_page)
    assert loaded_page.locator("#drawer-gene").text_content() == "APOE"
    assert "ε3/ε4" in loaded_page.locator("#drawer-ligature .lds-ligature-result").text_content()
    assert "3–4×" in loaded_page.locator("#drawer-apoe-risk-ratio").text_content()


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


RESULT_COUNT_IDS = ("count-state-observed", "count-state-negative", "count-state-gaps", "count-state-insufficient")
TAB_KEYS = ["every", "observed", "negative", "gaps", "insufficient", "carrier", "pathogenic", "acmg", "pgx", "risk"]


@pytest.mark.parametrize("sample", ["demo", "wildtype"])
def test_the_table_opens_on_every_check(loaded_page, sample):
    page = loaded_page
    page.set_input_files("#file-input", str(DEMO_FILE if sample == "demo" else FIXTURES / "wildtype-23andme.txt"))
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)  # no tab clicked: this is what the table opens on
    # The number of checks is the sum of the analysis's four per-result counts, read from the summary legend.
    checks = sum(_count(page, element_id) for element_id in RESULT_COUNT_IDS)
    assert checks > 0, "the analysis counted no checks, so this test proved nothing"
    rows = _shown_rows(page)
    ids = [row[0] for row in rows]
    assert len(ids) == len(set(ids)) == checks, f"{len(ids)} rows for {checks} checks: {ids}"
    by_state = _ids_by_state(page)
    assert sorted(ids) == sorted({i for state_ids in by_state.values() for i in state_ids}), ids
    # Each check is listed under its own word, so the default view holds every word the analysis counted.
    for _tab, state, word, count_id in STATE_TABS:
        assert [row[1] for row in rows].count(word) == _count(page, count_id), word
    assert page.locator("#showing-count").text_content() == f"Showing {checks} of {checks} checks"
    assert page.locator("[data-filter='every']").get_attribute("aria-pressed") == "true"
    assert "tab-active" in page.locator("[data-filter='every']").get_attribute("class").split()
    assert page.locator("[data-filter].tab-active").count() == 1


def test_the_tab_keys_are_new_and_the_old_all_key_is_gone(loaded_page):
    page = loaded_page
    _load_demo(page)
    assert page.eval_on_selector_all("[data-filter]", "els => els.map(e => e.dataset.filter)") == TAB_KEYS
    assert page.locator("[data-filter='all']").count() == 0
    assert page.evaluate("() => window.__lucidase.state.filterCategory") == "every"
    # The Found tab is its own key and lists only Found checks.
    page.locator("[data-filter='observed']").click()
    rows = _shown_rows(page)
    assert len(rows) == 10 and {row[1] for row in rows} == {"Found"}, rows
    assert page.evaluate("() => window.__lucidase.state.filterCategory") == "observed"


def test_the_result_tabs_work_from_the_keyboard(loaded_page):
    page = loaded_page
    _load_demo(page)
    page.locator("[data-filter='every']").focus()
    page.keyboard.press("Tab")
    expect(page.locator("[data-filter='observed']")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("[data-filter='observed']")).to_be_focused()
    assert {row[1] for row in _shown_rows(page)} == {"Found"}
    page.keyboard.press("Tab")
    expect(page.locator("[data-filter='negative']")).to_be_focused()
    page.keyboard.press("Space")
    expect(page.locator("[data-filter='negative']")).to_be_focused()
    assert {row[1] for row in _shown_rows(page)} == {"Not found"}
    assert page.locator("[data-filter='negative']").get_attribute("aria-pressed") == "true"
    assert page.locator("[data-filter='observed']").get_attribute("aria-pressed") == "false"
