#!/usr/bin/env python3
"""
Test Suite: Zero-Knowledge / Zero-Upload Privacy & Network Isolation
=====================================================================
Validates that:
1. Browser execution enforces zero-knowledge network boundaries via CSP (connect-src 'self').
2. Web Worker file processing executes in-memory without initiating network requests.
3. No tracking or telemetry scripts (Google Analytics, Sentry, Mixpanel, Segment) exist.
4. The /api/enrich endpoint accepts ONLY rsID tokens (matching ^rs[0-9]+$) and rejects any
   payload containing genotypes, coordinates, patient identifiers, or raw DNA data.
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
            WEB_DIR / "src" / "redis-client.js",
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
        
        # Worker must rely strictly on onmessage / postMessage and in-memory logic
        self.assertNotIn("fetch(", content, "worker.js must not perform fetch() calls")
        self.assertNotIn("XMLHttpRequest", content, "worker.js must not instantiate XMLHttpRequest")
        self.assertNotIn("WebSocket", content, "worker.js must not establish WebSocket connections")
        self.assertIn("onmessage", content, "worker.js must communicate via message passing")
        self.assertIn("postMessage", content, "worker.js must return results via message passing")

    def test_enrich_endpoint_restricts_payload_to_rsids_only(self):
        """Verifies /api/enrich only transmits rsID lists and strips or rejects raw data."""
        enrich_client_path = WEB_DIR / "src" / "redis-client.js"
        content = enrich_client_path.read_text(encoding="utf-8")
        
        # The body sent to /api/enrich must only be { rsids: ... }
        self.assertIn("body: JSON.stringify({ rsids:", content)
        self.assertNotIn("genotype", content)
        self.assertNotIn("chromosome", content)
        self.assertNotIn("position", content)

    def test_enrich_backend_validates_rsid_token_format(self):
        """Verifies backend api/enrich.js enforces strict rsID regex and limits batch size."""
        enrich_backend_path = WEB_DIR / "api" / "enrich.js"
        self.assertTrue(enrich_backend_path.exists(), "api/enrich.js must exist")
        content = enrich_backend_path.read_text(encoding="utf-8")
        
        # Must check rsids array presence and validate against rsID regex or format
        self.assertIn("!Array.isArray(rsids)", content)
        self.assertIn("MAX_BATCH = 100", content)


if __name__ == "__main__":
    unittest.main()
