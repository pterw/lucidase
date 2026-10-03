"""Browser test seam: serves web/ locally and drives it with Playwright Chromium.

Any uncaught page error or console error fails the test at teardown, unless the
test is marked ``allow_console_errors``. External hosts (CDN CSS, fonts) are
answered locally so tests never touch the network.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
DEMO_FILE = WEB_DIR / "demo-data" / "sample-23andme.txt"

# Stand-in for the Tailwind CDN script until the CSS is vendored: defines the
# global the inline config assigns to, and the one rule visibility checks need.
_TAILWIND_STUB = (
    "window.tailwind = {};"
    "document.head.appendChild(Object.assign(document.createElement('style'),"
    "{textContent: '.hidden{display:none}'}));"
)


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
    url = route.request.url
    if "cdn.tailwindcss.com" in url:
        route.fulfill(status=200, content_type="application/javascript", body=_TAILWIND_STUB)
    elif url.endswith(".css") or "typekit" in url:
        route.fulfill(status=200, content_type="text/css", body="")
    else:
        route.fulfill(status=200, body="")


@pytest.fixture
def page(browser, base_url, request):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.route(
        lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")),
        _stub_external,
    )
    pg = context.new_page()
    pg.base_url = base_url
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


@pytest.fixture
def loaded_page(page):
    page.goto(page.base_url, wait_until="networkidle")
    return page
