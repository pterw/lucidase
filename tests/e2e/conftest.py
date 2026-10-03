"""Browser test seam: serves web/ locally and drives it with Playwright Chromium.

Any uncaught page error or console error fails the test at teardown, unless the
test is marked ``allow_console_errors``. The Typekit host is answered locally and every other external
host is refused, so tests never touch the network.
"""

from __future__ import annotations

import functools
import http.server
import os
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
# One generous ceiling for every wait. Each wait returns as soon as its outcome
# holds, so a healthy run pays nothing; a loaded machine (worker start, parse,
# classify, render) gets time, and a real bug still fails, just later.
WAIT_TIMEOUT_MS = 20_000
expect.set_options(timeout=WAIT_TIMEOUT_MS)

DEMO_FILE = WEB_DIR / "demo-data" / "sample-23andme.txt"

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_console_errors: the test expects page errors / console errors",
    )


@pytest.fixture(scope="session")
def base_url():
    handler = functools.partial(_QuietHandler, directory=str(WEB_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


def _stub_external(route):
    # Only the Typekit font stylesheet is external; everything else is vendored,
    # so any other external request is a bug and is refused.
    if "typekit" in route.request.url:
        route.fulfill(status=200, content_type="text/css", body="")
    else:
        route.abort()


@pytest.fixture
def page(browser, base_url, request):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(
        lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")),
        _stub_external,
    )
    pg = context.new_page()
    pg.base_url = base_url
    # Stress seam (tests/e2e/stress_loop.py): slow the page's CPU to model a loaded machine.
    throttle = float(os.environ.get("E2E_CPU_THROTTLE", "1"))
    if throttle > 1:
        cdp = context.new_cdp_session(pg)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
    problems: list[str] = []
    pg.on("pageerror", lambda exc: problems.append(f"pageerror: {exc}"))

    def _on_console(msg):
        if msg.type != "error":
            return
        if "/favicon.ico" in (msg.location.get("url") or "") or "favicon.ico" in msg.text:
            return
        problems.append(f"console.error: {msg.text}")

    pg.on("console", _on_console)
    yield pg
    context.close()
    if request.node.get_closest_marker("allow_console_errors") is None and problems:
        pytest.fail("browser errors recorded:\n" + "\n".join(problems))


def goto_ready(page, url):
    """Load index.html and wait until the app is live.

    initApp binds every handler, then publishes window.__lucidase: an event sent
    before that (an upload, a click) would be lost, so wait for the outcome.
    """
    page.goto(url, wait_until="networkidle")
    page.wait_for_function("() => window.__lucidase !== undefined", timeout=WAIT_TIMEOUT_MS)


@pytest.fixture
def loaded_page(page):
    goto_ready(page, page.base_url)
    return page


# Real geometry, not a class-name proxy. The drawer slides in over 300 ms, so a
# state counts only once the box is identical on two consecutive animation frames:
# open = right edge at the viewport edge, closed = fully off the right edge.
_DRAWER_SETTLED = """(want) => {
  const el = document.getElementById('variant-drawer');
  const r = el.getBoundingClientRect();
  const prev = window.__drawerLeft;
  window.__drawerLeft = r.left;
  if (prev === undefined || Math.abs(prev - r.left) >= 0.5) return false;
  return want === 'open'
    ? r.width > 0 && Math.abs(r.right - window.innerWidth) < 1
    : r.left >= window.innerWidth;
}"""


def _wait_drawer(page, want, timeout):
    page.evaluate("delete window.__drawerLeft")
    page.wait_for_function(_DRAWER_SETTLED, arg=want, polling="raf", timeout=timeout)


def wait_drawer_open(page, timeout=WAIT_TIMEOUT_MS):
    _wait_drawer(page, "open", timeout)


def wait_drawer_closed(page, timeout=WAIT_TIMEOUT_MS):
    _wait_drawer(page, "closed", timeout)
