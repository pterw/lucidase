from __future__ import annotations

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE


def _assert_results_shown(page):
    expect(page.locator("#results-section")).to_be_visible(timeout=10000)
    assert page.locator("#variants-tbody tr").count() > 0


def test_demo_button_renders_results(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    _assert_results_shown(loaded_page)


def test_file_upload_renders_results(loaded_page):
    loaded_page.set_input_files("#file-input", str(DEMO_FILE))
    _assert_results_shown(loaded_page)


@pytest.mark.allow_console_errors
def test_worker_failure_is_visible(loaded_page):
    loaded_page.route(
        "**/src/worker.js",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body="throw new Error('boom from worker');",
        ),
    )
    loaded_page.reload(wait_until="networkidle")
    loaded_page.locator("#btn-load-demo").click()
    alert = loaded_page.locator("#analysis-error")
    expect(alert).to_be_visible(timeout=10000)
    assert alert.get_attribute("role") == "alert"
    assert alert.inner_text().strip() != ""
    expect(loaded_page.locator("#progress-section")).to_be_hidden()
