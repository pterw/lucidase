"""Page robustness: the drawer is reset per run, blocked storage and a throwing Worker
constructor are survived (S2b-C-2, C-3, C-4)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, WAIT_TIMEOUT_MS, goto_ready, wait_drawer_closed, wait_drawer_open

BAD_FILE = {"name": "bad.txt", "mimeType": "text/plain", "buffer": b"this is not a genome file\n"}


def test_drawer_closes_and_clears_when_a_bad_file_fails(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    loaded_page.locator("#variants-tbody tr").first.click()
    wait_drawer_open(loaded_page)
    loaded_page.set_input_files("#file-input", files=[BAD_FILE])
    expect(loaded_page.locator("#analysis-error")).to_be_visible()
    wait_drawer_closed(loaded_page)
    assert loaded_page.evaluate("window.__lucidase.state.selectedVariant") is None


def test_drawer_closes_when_a_new_run_starts(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    loaded_page.locator("#variants-tbody tr").first.click()
    wait_drawer_open(loaded_page)
    loaded_page.set_input_files("#file-input", str(DEMO_FILE))
    expect(loaded_page.locator("#results-section")).to_be_visible()
    wait_drawer_closed(loaded_page)
    assert loaded_page.evaluate("window.__lucidase.state.selectedVariant") is None


def test_blocked_storage_does_not_break_the_page(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(
        lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")),
        lambda route: route.fulfill(status=200, content_type="text/css", body="")
        if "typekit" in route.request.url
        else route.abort(),
    )
    context.add_init_script(
        """
        Storage.prototype.getItem = () => { throw new DOMException('blocked', 'SecurityError'); };
        Storage.prototype.setItem = () => { throw new DOMException('blocked', 'SecurityError'); };
        """
    )
    page = context.new_page()
    problems: list[str] = []
    page.on("pageerror", lambda exc: problems.append(f"pageerror: {exc}"))
    goto_ready(page, base_url)
    assert page.evaluate("window.__lucidase.state.theme") == "light"
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    page.locator("#btn-theme-toggle").click()
    assert page.evaluate("window.__lucidase.state.theme") == "dark"
    context.close()
    assert problems == []


@pytest.mark.allow_console_errors
def test_worker_constructor_failure_shows_the_alert_and_frees_the_inputs(page):
    page.add_init_script(
        "window.Worker = function () { throw new DOMException('no workers', 'SecurityError'); };"
    )
    goto_ready(page, page.base_url)
    page.set_input_files("#file-input", str(DEMO_FILE))
    expect(page.locator("#analysis-error")).to_be_visible()
    expect(page.locator("#progress-section")).to_be_hidden()
    expect(page.locator("#file-input")).to_be_enabled()
    expect(page.locator("#btn-load-demo")).to_be_enabled()
