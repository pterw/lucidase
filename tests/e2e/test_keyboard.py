"""Keyboard access: a results row opens its drawer, and the export items are reachable with Tab."""

from __future__ import annotations

from conftest import WAIT_TIMEOUT_MS, wait_drawer_closed, wait_drawer_open
from playwright.sync_api import expect

FIRST_ROW = "#variants-tbody tr:first-child"
MAX_TABS = 80


def _tab_until(page, selector):
    """Press Tab until the element matching selector holds focus (bounded, no sleeps)."""
    target = page.locator(selector).first
    for _ in range(MAX_TABS):
        page.keyboard.press("Tab")
        if target.evaluate("el => el === document.activeElement"):
            return
    raise AssertionError(f"Tab never reached {selector}")


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    expect(page.locator(FIRST_ROW)).to_be_visible()


def test_enter_opens_the_focused_row_and_closing_returns_focus_to_it(loaded_page):
    page = loaded_page
    _load_demo(page)
    row = page.locator(FIRST_ROW)
    rsid = row.locator("td").first.inner_text().strip()
    name = row.get_attribute("aria-label")
    assert rsid in name and row.locator("td").nth(1).inner_text().split()[0] in name

    _tab_until(page, FIRST_ROW)
    page.keyboard.press("Enter")
    wait_drawer_open(page)
    assert page.locator("#drawer-rsid").inner_text().strip() == rsid

    page.locator("#btn-close-drawer").focus()
    page.keyboard.press("Enter")
    wait_drawer_closed(page)
    assert row.evaluate("el => el === document.activeElement")


def test_space_opens_a_row_and_its_default_scroll_is_cancelled(loaded_page):
    page = loaded_page
    _load_demo(page)
    row = page.locator(FIRST_ROW)
    row.focus()
    # Headless Chromium does not scroll the page on Space from a focused row (the table's scroll
    # wrapper absorbs it), so assert the cancellation itself: the keydown reaches window prevented.
    page.evaluate(
        "() => { window.__spacePrevented = null;"
        " window.addEventListener('keydown', (e) => { if (e.key === ' ') window.__spacePrevented = e.defaultPrevented; }); }"
    )
    page.keyboard.press("Space")
    wait_drawer_open(page)
    assert page.evaluate("window.__spacePrevented") is True
    assert page.locator("#drawer-rsid").inner_text().strip() == row.locator("td").first.inner_text().strip()


def test_export_items_are_buttons_reached_by_tab_and_enter_downloads(loaded_page):
    page = loaded_page
    _load_demo(page)
    for item_id, suffix in (("btn-export-md", ".md"), ("btn-export-csv", ".csv")):
        assert page.locator(f"#{item_id}").evaluate("el => el.tagName") == "BUTTON"
        page.locator("main, body").first.evaluate("() => document.activeElement && document.activeElement.blur()")
        _tab_until(page, f"#{item_id}")
        with page.expect_download(timeout=WAIT_TIMEOUT_MS) as info:
            page.keyboard.press("Enter")
        assert info.value.suggested_filename.endswith(suffix)
