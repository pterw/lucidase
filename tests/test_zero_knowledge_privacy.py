#!/usr/bin/env python3
"""
Test Suite: Zero-Knowledge / Zero-Upload Privacy & Network Isolation
=====================================================================
Validates that:
1. Browser execution enforces zero-knowledge network boundaries via CSP (connect-src 'self').
2. Web Worker file processing executes in-memory without initiating network requests.
3. No tracking or telemetry scripts (Google Analytics, Sentry, Mixpanel, Segment) exist.
4. The client application NEVER transmits user variants or positive findings to any backend.
5. The /api/manifest endpoint returns static release provenance with zero input acceptance.
"""

import json
import re
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class TestZeroKnowledgePrivacy(unittest.TestCase):
    def test_csp_connect_src_isolation(self):
        """Verifies Content Security Policy forbids third-party exfiltration."""
        vercel_json_path = WEB_DIR / "vercel.json"
        self.assertTrue(vercel_json_path.exists(), "vercel.json must exist")

        with open(vercel_json_path, "r", encoding="utf-8") as f:
            vercel_config = json.load(f)

        csp_found = False
        for route in vercel_config.get("headers", []):
            for header in route.get("headers", []):
                if header["key"] == "Content-Security-Policy":
                    csp = header["value"]
                    csp_found = True
                    self.assertIn("connect-src 'self'", csp, "CSP must restrict network connections strictly to 'self'")
                    self.assertIn("frame-ancestors 'none'", csp, "CSP must prevent clickjacking via frame embedding")
        self.assertTrue(csp_found, "Content-Security-Policy header must be defined")

    def test_vercel_config_is_valid_and_ships_the_manifest_data(self):
        """routes/builds cannot sit beside headers on Vercel, or the CSP never ships (S5a-C-1)."""
        config = json.loads((WEB_DIR / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn("headers", config)
        for legacy in ("routes", "builds"):
            self.assertNotIn(legacy, config, f"vercel.json must not combine {legacy} with headers")
        function = config.get("functions", {}).get("api/manifest.js")
        self.assertIsNotNone(function, "functions must be keyed by api/manifest.js")
        source = (WEB_DIR / "api" / "manifest.js").read_text(encoding="utf-8")
        read = re.search(r'new URL\("(\.\./[^"]+)", import\.meta\.url\)', source)
        self.assertIsNotNone(read, "api/manifest.js must read its data through new URL(..., import.meta.url)")
        needed = (WEB_DIR / "api" / Path(read.group(1))).resolve().relative_to(WEB_DIR.resolve())
        self.assertEqual(function.get("includeFiles"), needed.as_posix())

    def test_no_telemetry_or_tracking_scripts(self):
        """Verifies absence of third-party analytics/telemetry trackers."""
        forbidden_patterns = [
            r"google-analytics\.com",
            r"googletagmanager\.com",
            r"mixpanel",
            r"segment\.io",
            r"amplitude\.com",
            r"hotjar",
            r"sentry\.io",
            r"datadoghq",
            r"loggly",
        ]

        target_files = [WEB_DIR / "index.html", *self._web_modules()]

        for file_path in target_files:
            self.assertTrue(file_path.exists(), f"File {file_path} must exist")
            content = file_path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                self.assertEqual(len(matches), 0, f"Found forbidden telemetry '{pattern}' in {file_path.name}")

    def test_worker_file_ingestion_is_offline(self):
        """Verifies worker.js contains 0 network dispatch functions (fetch/XMLHttpRequest/WebSocket)."""
        worker_path = WEB_DIR / "src" / "worker.js"
        content = worker_path.read_text(encoding="utf-8")

        self.assertNotIn("fetch(", content, "worker.js must not perform fetch() calls")
        self.assertNotIn("XMLHttpRequest", content, "worker.js must not instantiate XMLHttpRequest")
        self.assertNotIn("WebSocket", content, "worker.js must not establish WebSocket connections")
        self.assertIn("onmessage", content, "worker.js must communicate via message passing")
        self.assertIn("postMessage", content, "worker.js must return results via message passing")

    # Strings are matched first so a "//" inside a literal is not read as a comment;
    # string contents are kept, so self["fetch"] is still caught.
    _TOKEN_RE = re.compile(
        r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`|//[^\n]*|/\*.*?\*/",
        re.DOTALL,
    )
    _FORBIDDEN_NETWORK = [
        r"\bfetch\b",
        r"XMLHttpRequest",
        r"WebSocket",
        r"sendBeacon",
        r"EventSource",
        r"importScripts",
    ]
    _DYNAMIC_IMPORT_RE = re.compile(r"\bimport\s*\(")
    _KB_IMPORT_RE = re.compile(r"\bimport\s*\(\s*\"\./knowledge-base\.json\"")

    @staticmethod
    def _web_modules():
        """Every web/src/**/*.js outside vendor/ (the vendored CSS and fonts are not code we author)."""
        src = WEB_DIR / "src"
        modules = sorted(p for p in src.rglob("*.js") if "vendor" not in p.relative_to(src).parts)
        names = {p.name for p in modules}
        assert {"app.js", "worker.js", "view-model.js", "kb-loader.js", "parse.js"} <= names
        return modules

    @classmethod
    def _strip_comments(cls, source):
        def repl(match):
            text = match.group(0)
            return " " if text.startswith(("//", "/*")) else text

        return cls._TOKEN_RE.sub(repl, source)

    # The only fetch in the web app: a same-origin GET of the bundled demo file. Nothing else may use one.
    # karyogram-page.js does the same for its bundled synthetic sample (no user data, AGENTS.md section 5 allows
    # same-origin static assets). The URL lives in a const, so the const's literal path is pinned too.
    _FETCH_ALLOWED = {
        "app.js": [r'fetch\(\s*"\./demo-data/sample-23andme\.txt"\s*\)'],
        "karyogram-page.js": [
            r'const\s+SAMPLE_URL\s*=\s*"\./demo-data/sample-karyogram-23andme\.txt"\s*;',
            r"fetch\(\s*SAMPLE_URL\s*\)",
        ],
    }
    _UPLOAD_RE = re.compile(r"method\s*:|body\s*:", re.IGNORECASE)

    def test_no_network_primitives_in_any_web_module(self):
        """One comment-stripped scan over every web module bans network primitives and dynamic import()."""
        targets = self._web_modules()
        for path in targets:
            code = self._strip_comments(path.read_text(encoding="utf-8"))
            allowed_fetch = self._FETCH_ALLOWED.get(path.name, [])
            if allowed_fetch:
                for pattern in allowed_fetch:
                    self.assertEqual(len(re.findall(pattern, code)), 1, f"{path.name}: expected one allow-listed fetch")
                    code = re.sub(pattern, " ", code)
            for pattern in self._FORBIDDEN_NETWORK:
                self.assertIsNone(re.search(pattern, code), f"{path.name} must not use {pattern}")
            self.assertIsNone(
                self._UPLOAD_RE.search(code), f"{path.name} must not build a request with method: or body:"
            )

            dynamic_imports = len(self._DYNAMIC_IMPORT_RE.findall(code))
            allowed = 0
            if path.name == "kb-loader.js":
                allowed = len(self._KB_IMPORT_RE.findall(code))
                self.assertEqual(allowed, 1, 'kb-loader.js must import "./knowledge-base.json" exactly once')
            self.assertEqual(
                dynamic_imports,
                allowed,
                f"{path.name} has an import() beyond the one literal ./knowledge-base.json load",
            )

    def test_manifest_endpoint_guarantees(self):
        """Verifies backend api/manifest.js serves manifest with verifiable privacy guarantees."""
        manifest_backend_path = WEB_DIR / "api" / "manifest.js"
        self.assertTrue(manifest_backend_path.exists(), "api/manifest.js must exist")
        content = manifest_backend_path.read_text(encoding="utf-8")

        # Must declare honest verifiable privacy guarantees
        self.assertIn("local_analysis: true", content)
        self.assertIn("genomic_uploads: false", content)
        self.assertIn("variant_identifiers_transmitted: false", content)
        # Release facts are read from knowledge-base.json (web/tests/manifest.test.mjs), not asserted as constants.


if __name__ == "__main__":
    unittest.main()
