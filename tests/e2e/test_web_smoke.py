from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, goto_ready


def _assert_results_shown(page):
    expect(page.locator("#results-section")).to_be_visible()
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
    goto_ready(page, page.base_url)
    alert = page.locator("#analysis-error")
    # Causality: nothing is shown until the user starts an analysis.
    expect(alert).to_be_hidden()
    page.locator("#btn-load-demo").click()
    expect(alert).to_be_visible()
    assert alert.get_attribute("role") == "alert"
    assert alert.inner_text().strip() != ""
    expect(page.locator("#progress-section")).to_be_hidden()
    expect(page.locator("#results-section")).to_be_hidden()


@pytest.mark.allow_console_errors
def test_retry_after_worker_failure_recovers(page):
    _serve_worker(page, FAILING_WORKER)
    goto_ready(page, page.base_url)
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible()
    page.unroute("**/src/worker.js")
    page.locator("#btn-load-demo").click()
    _assert_results_shown(page)
    expect(page.locator("#analysis-error")).to_be_hidden()


@pytest.mark.allow_console_errors
def test_retry_with_still_failing_worker_shows_error_again(page):
    worker_requests = []
    page.on(
        "request",
        lambda req: worker_requests.append(req.url) if req.url.endswith("/src/worker.js") else None,
    )
    _serve_worker(page, FAILING_WORKER)
    goto_ready(page, page.base_url)
    for run in (1, 2):
        # Run N has demonstrably started once its worker has been requested; processText
        # clears the previous alert before that, so a visible alert after it is run N's own.
        with page.expect_request(lambda req: req.url.endswith("/src/worker.js")):
            page.locator("#btn-load-demo").click()
        assert len(worker_requests) >= run, f"run {run} never started a worker"
        expect(page.locator("#analysis-error")).to_be_visible()
        expect(page.locator("#progress-section")).to_be_hidden()
        page.wait_for_function("() => !document.getElementById('btn-load-demo').disabled")


def test_silent_worker_times_out_visibly(page):
    _serve_worker(page, SILENT_WORKER)
    goto_ready(page, page.base_url)
    page.evaluate("window.__lucidase.state.workerTimeoutMs = 500")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible()
    expect(page.locator("#progress-section")).to_be_hidden()


STALLING_WORKER = (
    "self.onmessage = () => "
    "self.postMessage({type: 'progress', percent: 5, status: 'x'});"
)
# The watchdog timeout is wall-clock while E2E_CPU_THROTTLE slows the page's main thread, so
# the timeout scales with the throttle and the run always outlasts it by half (the property
# under test: progress ticks every 150 ms keep a shorter-than-the-run watchdog quiet).
THROTTLE = max(1.0, float(os.environ.get("E2E_CPU_THROTTLE", "1")))
HEALTHY_TIMEOUT_MS = int(500 * THROTTLE)
HEALTHY_TICKS = int(HEALTHY_TIMEOUT_MS * 1.5 / 150) + 1
SLOW_HEALTHY_WORKER = """
self.onmessage = () => {
  let n = 0;
  const t = setInterval(() => {
    self.postMessage({type: 'progress', percent: 10 + n, status: 'working'});
    if (++n >= __TICKS__) {
      clearInterval(t);
      self.postMessage({type: 'error', message: 'finished healthy run'});
    }
  }, 150);
};
""".replace("__TICKS__", str(HEALTHY_TICKS))


def test_worker_stall_after_progress_times_out_visibly(page):
    _serve_worker(page, STALLING_WORKER)
    goto_ready(page, page.base_url)
    page.evaluate("window.__lucidase.state.workerTimeoutMs = 500")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible()
    expect(page.locator("#progress-section")).to_be_hidden()


@pytest.mark.allow_console_errors
def test_watchdog_does_not_fire_during_healthy_progress(page):
    _serve_worker(page, SLOW_HEALTHY_WORKER)
    goto_ready(page, page.base_url)
    page.evaluate(f"window.__lucidase.state.workerTimeoutMs = {HEALTHY_TIMEOUT_MS}")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible()
    # The alert must be the worker's own message, not the watchdog's.
    assert "finished healthy run" in page.locator("#analysis-error-detail").inner_text()


@pytest.mark.allow_console_errors
def test_transient_module_load_failure_is_retried_once(loaded_page):
    # A worker whose module graph fails to load (the machine ran out of socket buffers,
    # the network dropped a request) raises an error event with no message. That is a
    # transient start failure: the run starts a fresh worker once instead of failing.
    aborted = []

    def flaky(route):
        if aborted:
            route.continue_()
        else:
            aborted.append(route.request.url)
            route.abort("connectionreset")

    loaded_page.route("**/src/core/classify.js", flaky)
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    assert len(aborted) == 1


@pytest.mark.allow_console_errors
def test_persistent_module_load_failure_still_shows_the_alert(loaded_page):
    loaded_page.route("**/src/core/classify.js", lambda route: route.abort("connectionreset"))
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#analysis-error")).to_be_visible()
    expect(loaded_page.locator("#results-section")).to_be_hidden()
    expect(loaded_page.locator("#btn-load-demo")).to_be_enabled()
