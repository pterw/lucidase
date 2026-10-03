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

        target_files = [
            WEB_DIR / "index.html",
            WEB_DIR / "src" / "app.js",
            WEB_DIR / "src" / "worker.js",
            WEB_DIR / "src" / "kb-loader.js",
            *sorted((WEB_DIR / "src" / "core").glob("*.js")),
        ]

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

    @classmethod
    def _strip_comments(cls, source):
        def repl(match):
            text = match.group(0)
            return " " if text.startswith(("//", "/*")) else text

        return cls._TOKEN_RE.sub(repl, source)

    def test_no_network_primitives_in_worker_loader_or_core(self):
        """One comment-stripped scan bans network primitives and dynamic import() across the offline code."""
        src = WEB_DIR / "src"
        targets = [
            src / "worker.js",
            src / "kb-loader.js",
            *sorted((src / "core").glob("*.js")),
        ]
        self.assertGreater(len(targets), 2, "core/*.js must be found")

        for path in targets:
            self.assertTrue(path.exists(), f"File {path} must exist")
            code = self._strip_comments(path.read_text(encoding="utf-8"))
            for pattern in self._FORBIDDEN_NETWORK:
                self.assertIsNone(re.search(pattern, code), f"{path.name} must not use {pattern}")

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

    def test_app_does_not_exfiltrate_user_variant_findings(self):
        """Verifies app.js does not transmit positive findings or state.records over the network."""
        app_path = WEB_DIR / "src" / "app.js"
        content = app_path.read_text(encoding="utf-8")

        # Must not map records to POST body
        self.assertNotIn("state.records.map(", content, "app.js must not map state.records to network payload")
        self.assertNotIn("triggerRedisEnrichment", content, "Leaky enrichment trigger must be removed")

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
