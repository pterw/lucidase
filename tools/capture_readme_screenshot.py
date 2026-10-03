"""Capture the README screenshots (light and dark) of the Lucidase web app.

Run `python tools/capture_readme_screenshot.py` to write
`docs/assets/lucidase-screenshot-light.png` and `docs/assets/lucidase-screenshot-dark.png`, and the
karyogram page (karyogram.html, synthetic sample loaded) to `docs/assets/lucidase-karyogram-light.png` and
`docs/assets/lucidase-karyogram-dark.png`.

The script serves `web/` on an ephemeral localhost port, loads the bundled synthetic
demo sample and captures the analysis results at 1440x900. It runs offline: the Typekit
stylesheet is answered with an empty CSS file and every other non-localhost request is
aborted, so the page renders with fallback fonts.

This is a manual dev tool whose output is reviewed visually. It has no automated test.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"
OUT_DIR = REPO_ROOT / "docs" / "assets"
VIEWPORT = {"width": 1440, "height": 900}


class _Handler(http.server.SimpleHTTPRequestHandler):
    # Explicit types so ES modules and JSON modules load even where the OS registry
    # (Windows) maps .js to text/plain.
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
        ".css": "text/css",
        ".svg": "image/svg+xml",
    }

    def log_message(self, format, *args):  # noqa: A002
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def _is_local(url: str) -> bool:
    if url.startswith(("data:", "blob:")):
        return True
    return urlparse(url).hostname in ("127.0.0.1", "localhost")


def _route(route: Route) -> None:
    url = route.request.url
    if _is_local(url):
        route.continue_()
    elif "typekit" in url:
        route.fulfill(status=200, content_type="text/css", body="")
    else:
        route.abort()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(_Handler, directory=str(WEB_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport=VIEWPORT, device_scale_factor=1, reduced_motion="reduce"
            )
            context.route("**/*", _route)
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            page.click("#btn-load-demo")
            page.wait_for_selector("#results-section", state="visible")
            # Put the top of the results a few pixels under the sticky header, measured
            # in the page, so no sliver of the section above shows through.
            page.evaluate(
                """() => {
                    const header = document.querySelector('header');
                    const results = document.getElementById('results-section');
                    const gap = 8;
                    const top = results.getBoundingClientRect().top + window.scrollY;
                    window.scrollTo(0, top - header.getBoundingClientRect().height - gap);
                }"""
            )
            page.mouse.move(0, 0)
            for theme in ("light", "dark"):
                page.evaluate(f"window.__lucidase.setTheme('{theme}')")
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT_DIR / f"lucidase-screenshot-{theme}.png"))
            page.goto(f"{url}/karyogram.html", wait_until="networkidle")
            page.click("#btn-load-karyogram-sample")
            page.wait_for_selector("#karyogram-totals", state="visible")
            page.mouse.move(0, 0)
            for theme in ("light", "dark"):
                if page.get_attribute("html", "data-theme") != theme:
                    page.click("#btn-theme-toggle")
                page.mouse.move(0, 0)
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT_DIR / f"lucidase-karyogram-{theme}.png"))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
