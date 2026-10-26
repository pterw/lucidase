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


# What the Found tab shows for the demo, with each row's KB category as the table's tag says it (the table has no
# category tabs: the category is read off the row). The demo's HFE H63D (rs1799945) and MTHFR (rs1801133) are variant
# readings with unclear evidence, so they are under Unclear, not here. The wild-type fixture has no found variant.
DEMO_FOUND_CATEGORIES = {
    "APOE (rs429358 + rs7412)": "Risk Factor",
    "rs3918290": "Pharmacogenomics",
    "rs6025": "Risk Factor",
    "rs1799963": "Risk Factor",
    "rs4149056": "Pharmacogenomics",
    "rs4244285": "Pharmacogenomics",
    "rs113993960": "Carrier",
    "rs9923231": "Pharmacogenomics",
    "rs1800562": "Carrier",
    "rs4988235": "Trait",
}
DEMO_FILTER_ROWS = {"observed": set(DEMO_FOUND_CATEGORIES)}


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


def test_found_rows_say_their_category_and_agree_with_the_report_groups(loaded_page):
    page = loaded_page
    _load_demo(page)
    page.locator("[data-filter='observed']").click()
    rows = _shown_rows(page)
    found = {row[0] for row in rows}
    assert len(found) == len(rows) == _count(page, "count-state-observed") == 10
    # The category is read off each row's own tag, not from a tab.
    categories = page.evaluate(
        "() => Object.fromEntries([...document.querySelectorAll('#variants-tbody tr')]"
        ".map(r => [r.children[0].textContent.trim(),"
        " r.children[5].querySelector('.lds-tag[class*=\"lds-tag-cat-\"]').textContent.trim()]))"
    )
    assert categories == DEMO_FOUND_CATEGORIES
    # The report groups hold the same Found checks, one row each, each as a Found row.
    assert page.locator("#report-groups article.lds-finding:has(> span.lds-mark-supported_and_observed)").count() == 10
    for rsid in found:
        report_row = page.locator(f'#report-groups article.lds-finding[data-finding-id="{rsid}"]')
        expect(report_row.locator(":scope > span.lds-mark-supported_and_observed")).to_have_count(1)
    assert {row[1] for row in rows} == {"Found"}
    assert page.locator("#showing-count").text_content() == "Showing 10 of 10 findings"


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
TAB_KEYS = ["every", "observed", "negative", "gaps", "insufficient"]


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


def test_there_is_no_category_tab_and_no_acmg_tab(loaded_page):
    page = loaded_page
    _load_demo(page)
    for key in ("pathogenic", "carrier", "pgx", "risk", "acmg"):
        assert page.locator(f"[data-filter='{key}']").count() == 0, key
    tabs = page.locator("#table-panel .lds-tabs")
    text = tabs.inner_text().lower()
    for word in ("acmg", "pathogenic", "carrier", "pharmacogenomics", "risk factors"):
        assert word not in text, f"{word!r} in the tabs: {text}"
    assert tabs.locator("button").count() == 5


@pytest.mark.parametrize("sample", ["demo", "wildtype"])
def test_each_tab_counts_the_rows_it_shows(loaded_page, sample):
    page = loaded_page
    page.set_input_files("#file-input", str(DEMO_FILE if sample == "demo" else FIXTURES / "wildtype-23andme.txt"))
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)
    seen = {}
    for key in TAB_KEYS:
        tab = page.locator(f"[data-filter='{key}']")
        tab.click()
        shown = len(_shown_rows(page))  # measured from the table, not from the count's own source
        printed = tab.locator(".lds-tab-count").text_content().strip()
        assert printed == str(shown), f"{key}: tab says {printed}, the table shows {shown}"
        seen[key] = shown
    # The result tabs say the summary legend's own figures, and "All" is their sum.
    for key, count_id in zip(TAB_KEYS[1:], RESULT_COUNT_IDS):
        assert seen[key] == _count(page, count_id), key
    assert seen["every"] == sum(seen[key] for key in TAB_KEYS[1:])
    assert sum(1 for count in seen.values() if count) >= 2, "too few non-empty tabs for this to prove anything"
    # Searching narrows the rows, not the tab counts (they describe the analysis).
    page.locator("[data-filter='every']").click()
    page.locator("#search-input").fill("rs4244285")
    assert len(_shown_rows(page)) <= 1
    assert page.locator("[data-filter='every'] .lds-tab-count").text_content().strip() == str(seen["every"])


@pytest.mark.allow_console_errors
def test_an_unknown_tab_key_is_a_visible_error_and_leaves_the_table_alone(loaded_page):
    page = loaded_page
    _load_demo(page)
    before = _shown_rows(page)
    assert before, "the table showed no rows, so this test proved nothing"
    page.evaluate("() => { window.__lucidase.state.filterCategory = 'all'; }")  # the retired key
    with page.expect_event("pageerror") as raised:
        page.locator("#search-input").fill("rs")  # any search re-renders the table
    assert 'unknown table tab "all"' in raised.value.message
    # The guard runs before the table is cleared: a bad key never leaves an empty table behind.
    assert _shown_rows(page) == before


def test_a_tab_count_with_no_figure_is_a_visible_error(loaded_page):
    page = loaded_page
    page.evaluate(
        "() => { const s = document.createElement('span'); s.dataset.tabCount = 'bogus'; document.body.append(s); }"
    )
    page.set_input_files("#file-input", str(DEMO_FILE))
    # The page's one error path shows it: the analysis alert names the tab, and no results are shown.
    expect(page.locator("#analysis-error-detail")).to_contain_text('no count for table tab "bogus"')
    expect(page.locator("#results-section")).to_be_hidden()


def test_the_tab_counts_follow_a_second_analysis(loaded_page):
    page = loaded_page
    _load_demo(page)

    def printed():
        return {key: int(page.locator(f"[data-filter='{key}'] .lds-tab-count").text_content().replace(",", ""))
                for key in TAB_KEYS}

    first = printed()
    assert first["observed"] == STATE_TAB_COUNTS["demo"]["observed"]
    page.set_input_files("#file-input", str(FIXTURES / "wildtype-23andme.txt"))
    expect(page.locator("[data-filter='observed'] .lds-tab-count")).to_have_text("0")
    second = printed()
    legend = {key: _count(page, count_id) for key, count_id in zip(TAB_KEYS[1:], RESULT_COUNT_IDS)}
    assert second == {"every": sum(legend.values()), **legend}
    assert second != first
    for tab, _state, _word, _count_id in STATE_TABS:
        assert second[tab] == STATE_TAB_COUNTS["wildtype"][tab], tab
