"""CSP, third-party isolation and cache headers (P1-031, P1-032).

The test server applies the exact headers from web/vercel.json, matched by path
pattern, so the page is exercised under the production CSP.
"""

from __future__ import annotations

import functools
import http.server
import json
import re
import threading
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from conftest import WEB_DIR

TYPEKIT_HOSTS = {"use.typekit.net", "p.typekit.net"}
VIOLATION_LISTENER = """
window.__cspViolations = [];
document.addEventListener('securitypolicyviolation', e =>
  window.__cspViolations.push(e.violatedDirective + ' ' + e.blockedURI));
"""


def _vercel_rules():
    config = json.loads((WEB_DIR / "vercel.json").read_text(encoding="utf-8"))
    return [
        (re.compile("^" + rule["source"] + "$"), {h["key"]: h["value"] for h in rule["headers"]})
        for rule in config["headers"]
    ]


def _headers_for(path, rules):
    merged: dict[str, str] = {}
    for pattern, headers in rules:
        if pattern.match(path):
            merged.update(headers)
    return merged


class _VercelHandler(http.server.SimpleHTTPRequestHandler):
    rules: list = []

    def log_message(self, format, *args):  # noqa: A002
        pass

    def end_headers(self):
        for key, value in _headers_for(urlsplit(self.path).path, self.rules).items():
            self.send_header(key, value)
        super().end_headers()


@pytest.fixture(scope="module")
def vercel_url():
    handler = type("H", (_VercelHandler,), {"rules": _vercel_rules()})
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(handler, directory=str(WEB_DIR))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _directive(csp, name):
    for part in csp.split(";"):
        tokens = part.split()
        if tokens and tokens[0] == name:
            return tokens[1:]
    raise AssertionError(f"CSP has no {name} directive: {csp}")


def _csp():
    rules = _vercel_rules()
    return _headers_for("/", rules)["Content-Security-Policy"]


def test_script_src_is_self_only():
    tokens = _directive(_csp(), "script-src")
    assert "'unsafe-inline'" not in tokens
    assert tokens == ["'self'"], f"script-src allows more than self: {tokens}"


def test_no_third_party_host_outside_typekit_in_csp():
    csp = _csp()
    for host in re.findall(r"https?://([^\s;/]+)", csp):
        assert host in TYPEKIT_HOSTS, f"CSP allows third-party host {host}"


def test_src_is_not_cached_immutably():
    rules = _vercel_rules()
    value = _headers_for("/src/app.js", rules).get("Cache-Control", "")
    assert "immutable" not in value, value
    match = re.search(r"max-age=(\d+)", value)
    assert match is None or int(match.group(1)) <= 3600, value


def test_demo_renders_under_production_csp(browser, vercel_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    foreign: list[str] = []

    def _external(route):
        host = urlsplit(route.request.url).hostname
        foreign.append(route.request.url)
        if host in TYPEKIT_HOSTS:
            route.fulfill(status=200, content_type="text/css", body="")
        else:
            route.abort()

    context.route(lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")), _external)
    context.add_init_script(VIOLATION_LISTENER)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(vercel_url, wait_until="networkidle")
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible(timeout=10000)
    assert page.locator("#variants-tbody tr").count() > 0
    violations = page.evaluate("window.__cspViolations")
    context.close()
    assert not violations, f"CSP violations: {violations}"
    assert not errors, errors
    other = [u for u in foreign if urlsplit(u).hostname not in TYPEKIT_HOSTS]
    assert not other, f"requests to third-party hosts: {other}"


def test_dockerfile_asset_location_repeats_security_headers_and_csp():
    """nginx add_header in a location replaces the server-level ones."""
    text = (WEB_DIR / "Dockerfile").read_text(encoding="utf-8")
    server, _, rest = text.partition("location / {")
    location = rest[rest.index("location ~*"):]
    location = location[: location.index("}")]
    headers = re.findall(r"add_header (\S+) ", server)
    assert {"X-Content-Type-Options", "Content-Security-Policy"} <= set(headers)
    for name in headers:
        assert f"add_header {name} " in location, f"asset location drops {name}"
    csp = re.search(r'add_header Content-Security-Policy "([^"]+)"', location).group(1)
    assert csp == _csp(), "Dockerfile CSP differs from vercel.json"
    assert 'add_header Cache-Control "no-cache"' in location
