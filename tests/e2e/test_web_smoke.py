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


FAILING_WORKER = "throw new Error('boom from worker');"
SILENT_WORKER = "// loads fine but never answers"


def _serve_worker(page, body):
    page.route(
        "**/src/worker.js",
        lambda route: route.fulfill(
            status=200, content_type="application/javascript", body=body
        ),
    )


@pytest.mark.allow_console_errors
def test_worker_failure_is_visible(page):
    _serve_worker(page, FAILING_WORKER)
    page.goto(page.base_url, wait_until="networkidle")
    alert = page.locator("#analysis-error")
    # Causality: nothing is shown until the user starts an analysis.
    expect(alert).to_be_hidden()
    page.locator("#btn-load-demo").click()
    expect(alert).to_be_visible(timeout=10000)
    assert alert.get_attribute("role") == "alert"
    assert alert.inner_text().strip() != ""
    expect(page.locator("#progress-section")).to_be_hidden()
    expect(page.locator("#results-section")).to_be_hidden()


@pytest.mark.allow_console_errors
def test_retry_after_worker_failure_recovers(page):
    _serve_worker(page, FAILING_WORKER)
    page.goto(page.base_url, wait_until="networkidle")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible(timeout=10000)
    page.unroute("**/src/worker.js")
    page.locator("#btn-load-demo").click()
    _assert_results_shown(page)
    expect(page.locator("#analysis-error")).to_be_hidden()


@pytest.mark.allow_console_errors
def test_retry_with_still_failing_worker_shows_error_again(page):
    _serve_worker(page, FAILING_WORKER)
    page.goto(page.base_url, wait_until="networkidle")
    for _ in range(2):
        page.locator("#btn-load-demo").click()
        expect(page.locator("#analysis-error")).to_be_visible(timeout=10000)
        expect(page.locator("#progress-section")).to_be_hidden()
        # The alert is cleared at run start, so a visible alert is a fresh one.
        page.wait_for_function(
            "() => !document.getElementById('btn-load-demo').disabled", timeout=5000
        )


def test_silent_worker_times_out_visibly(page):
    _serve_worker(page, SILENT_WORKER)
    page.goto(page.base_url, wait_until="networkidle")
    page.evaluate("window.__lucidase.state.workerTimeoutMs = 500")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible(timeout=10000)
    expect(page.locator("#progress-section")).to_be_hidden()


STALLING_WORKER = (
    "self.onmessage = () => "
    "self.postMessage({type: 'progress', percent: 5, status: 'x'});"
)
# Posts progress every 150 ms for ~1.2 s (longer than the 500 ms timeout), then completes.
SLOW_HEALTHY_WORKER = """
self.onmessage = () => {
  let n = 0;
  const t = setInterval(() => {
    self.postMessage({type: 'progress', percent: 10 + n, status: 'working'});
    if (++n >= 8) {
      clearInterval(t);
      self.postMessage({type: 'error', message: 'finished healthy run'});
    }
  }, 150);
};
"""


def test_worker_stall_after_progress_times_out_visibly(page):
    _serve_worker(page, STALLING_WORKER)
    page.goto(page.base_url, wait_until="networkidle")
    page.evaluate("window.__lucidase.state.workerTimeoutMs = 500")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible(timeout=10000)
    expect(page.locator("#progress-section")).to_be_hidden()


@pytest.mark.allow_console_errors
def test_watchdog_does_not_fire_during_healthy_progress(page):
    _serve_worker(page, SLOW_HEALTHY_WORKER)
    page.goto(page.base_url, wait_until="networkidle")
    page.evaluate("window.__lucidase.state.workerTimeoutMs = 500")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible(timeout=10000)
    # The alert must be the worker's own message, not the watchdog's.
    assert "finished healthy run" in page.locator("#analysis-error-detail").inner_text()
