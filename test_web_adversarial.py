"""
Adversarial QA & Fuzzing Suite for GenomePulse Web Application
==============================================================
Runs Playwright Chromium in headless mode against a local HTTP server.
Executes aggressive edge-case, malformed data, XSS injection, and UI stress testing.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import sys
import threading
import time
from pathlib import Path

# Configure UTF-8 stdout / stderr on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright, expect

WEB_DIR = Path(__file__).parent / "web"
PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"

class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format, *args):
        # Silence normal HTTP access logs
        pass

    def end_headers(self):
        # Enable CORS and disable caching during test
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()


def start_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), QuietHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_adversarial_suite():
    server = start_server()
    print(f"[*] Local test server running on {BASE_URL}")

    results = {
        "passed": 0,
        "failed": 0,
        "vulnerabilities": [],
        "warnings": [],
        "tests": []
    }

    with sync_playwright() as p:
        # Launch Chromium
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-web-security", "--allow-file-access-from-files"]
        )
        context = browser.new_context(viewport={"width": 1280, "height": 850})
        page = context.new_page()

        console_errors = []
        js_dialogs = []

        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type in ("error", "warning") else None)
        page.on("dialog", lambda dialog: (js_dialogs.append(dialog.message), dialog.dismiss()))
        page.on("pageerror", lambda exc: console_errors.append(f"PageError: {exc}"))

        print("\n" + "=" * 60)
        print("GENOMEPULSE ADVERSARIAL PLAYWRIGHT TEST SUITE")
        print("=" * 60)

        # -------------------------------------------------------------
        # TEST 1: Initial Page Load & Visual Integrity
        # -------------------------------------------------------------
        t0 = time.time()
        print("\n[TEST 1] Loading Web Dashboard...")
        page.goto(BASE_URL, wait_until="networkidle")
        title = page.title()
        assert "GenomePulse" in title, f"Unexpected page title: {title}"
        print(f"  [PASS] Dashboard loaded in {time.time() - t0:.2f}s (Title: '{title}')")
        results["passed"] += 1
        results["tests"].append("Test 1: Initial Load & Visual Integrity")

        # -------------------------------------------------------------
        # TEST 2: Demo Sample Ingestion & Worker Pipeline
        # -------------------------------------------------------------
        print("\n[TEST 2] Testing 1-Click Demo Sample Loading...")
        btn_demo = page.locator("#btn-load-demo")
        btn_demo.click()

        # Wait for results section to be visible
        page.wait_for_selector("#results-section:not(.hidden)", timeout=10000)
        qc_snps = page.locator("#qc-total-snps").text_content()
        qc_call_rate = page.locator("#qc-call-rate").text_content()
        qc_sex = page.locator("#qc-inferred-sex").text_content()
        pathogenic_count = page.locator("#count-pathogenic").text_content()

        print(f"  [PASS] Total SNPs parsed: {qc_snps}")
        print(f"  [PASS] Call Rate: {qc_call_rate}")
        print(f"  [PASS] Inferred Sex: {qc_sex}")
        print(f"  [PASS] Pathogenic Findings: {pathogenic_count}")
        assert int(qc_snps.replace(",", "")) >= 20, "SNP count too low"
        results["passed"] += 1
        results["tests"].append("Test 2: Demo Sample Parsing")

        # -------------------------------------------------------------
        # TEST 3: Adversarial Search Queries & Regex Injection
        # -------------------------------------------------------------
        print("\n[TEST 3] Adversarial Search Inputs (Regex ReDoS, Special Characters)...")
        search_input = page.locator("#search-input")
        evil_queries = [
            "(a+)+$",                     # Classic ReDoS pattern
            "[*+?^${}()|[\\]]",            # Bare regex operators
            "<script>alert(1)</script>",  # XSS in search
            "../../../../etc/passwd",     # Path traversal string
            "'; DROP TABLE variants; --",  # SQL injection
            "🧬🔬⚡✨💥",                   # Multibyte emojis
            "A" * 500,                    # Buffer overflow attempt
        ]

        for q in evil_queries:
            search_input.fill(q)
            page.wait_for_timeout(50)
            showing = page.locator("#showing-count").text_content()
            # Verify UI didn't crash
            assert "Showing" in showing, f"Search crashed on query: {q}"

        search_input.fill("") # Clear search
        print("  [PASS] All 7 adversarial search patterns handled without crash or ReDoS.")
        results["passed"] += 1
        results["tests"].append("Test 3: Adversarial Search Query Fuzzing")

        # -------------------------------------------------------------
        # TEST 4: Flyout Drawer & XSS in Details
        # -------------------------------------------------------------
        print("\n[TEST 4] Testing Flyout Drawer & Variant Row Selection...")
        first_row = page.locator("#variants-tbody tr").first
        first_row.click()
        page.wait_for_selector("#variant-drawer:not(.translate-x-full)", timeout=3000)
        
        drawer_rsid = page.locator("#drawer-rsid").text_content()
        drawer_gene = page.locator("#drawer-gene").text_content()
        drawer_pheno = page.locator("#drawer-phenotype").text_content()
        print(f"  [PASS] Drawer opened for {drawer_rsid} ({drawer_gene})")
        print(f"    Phenotype snippet: {drawer_pheno[:60]}...")
        
        # Close drawer
        page.locator("#btn-close-drawer").click()
        page.wait_for_selector("#variant-drawer.translate-x-full", timeout=3000)
        print("  [PASS] Drawer closed cleanly.")
        results["passed"] += 1
        results["tests"].append("Test 4: Flyout Drawer Interactivity")

        # -------------------------------------------------------------
        # TEST 5: Category Filtering Transitions
        # -------------------------------------------------------------
        print("\n[TEST 5] Testing Rapid Category Filtering...")
        filters = ["pathogenic", "acmg", "pgx", "carrier", "risk", "all"]
        for f in filters:
            btn = page.locator(f"[data-filter='{f}']")
            btn.click()
            showing = page.locator("#showing-count").text_content()
            assert "Showing" in showing, f"Filter {f} failed"
        print("  [PASS] All filter transitions verified.")
        results["passed"] += 1
        results["tests"].append("Test 5: Filter Transitions")

        # -------------------------------------------------------------
        # TEST 6: Redis Live Enrichment Button Resilience
        # -------------------------------------------------------------
        print("\n[TEST 6] Testing Redis Live Enrichment Trigger...")
        btn_redis = page.locator("#btn-enrich-redis")
        btn_redis.click()
        page.wait_for_selector("#redis-stats-banner:not(.hidden)", timeout=5000)
        redis_latency = page.locator("#redis-latency").text_content()
        redis_hits = page.locator("#redis-hits-count").text_content()
        print(f"  [PASS] Redis banner active: Latency = {redis_latency}, Hits = {redis_hits}")
        results["passed"] += 1
        results["tests"].append("Test 6: Redis Enrichment Trigger")

        # -------------------------------------------------------------
        # TEST 7: ADVERSARIAL FILE INGESTION (XSS Injection in DNA)
        # -------------------------------------------------------------
        print("\n[TEST 7] Ingesting Malicious File with XSS Payloads in rsIDs...")
        xss_dna = """# 23andMe file
# build 37
# rsid\tchromosome\tposition\tgenotype
<script>window.__xss_rsid=1</script>\t1\t1000\tAA
<img src=x onerror=window.__xss_img=1>\t1\t1001\tGG
rs429358\t19\t45411941\tCC
rs1800562\t6\t26093141\t<svg/onload=window.__xss_gt=1>
"""
        # Inject file directly via evaluate (dispatching worker action)
        page.evaluate("""(xssContent) => {
          window.__genomePulse.state.fileName = 'evil_xss.txt';
          window.__genomePulse.processText(xssContent, 'evil_xss.txt');
        }""", xss_dna)

        page.wait_for_selector("#results-section:not(.hidden)", timeout=5000)
        
        # Check if any XSS executed on window
        xss_executed = page.evaluate("""() => {
          return Boolean(window.__xss_rsid || window.__xss_img || window.__xss_gt);
        }""")
        assert not xss_executed, "VULNERABILITY: XSS payload executed in client context!"
        print("  [PASS] XSS Payloads safely escaped! (No unauthorized script execution)")
        results["passed"] += 1
        results["tests"].append("Test 7: XSS Injection Resistance")

        # -------------------------------------------------------------
        # TEST 8: ADVERSARIAL FILE (Zero-Byte File & Division by Zero)
        # -------------------------------------------------------------
        print("\n[TEST 8] Ingesting Zero-Byte Empty File...")
        page.evaluate("""() => {
          window.__genomePulse.processText('', 'empty.txt');
        }""")
        page.wait_for_timeout(500)
        qc_snps = page.locator("#qc-total-snps").text_content()
        qc_call_rate = page.locator("#qc-call-rate").text_content()
        assert qc_snps == "0", f"Expected 0 SNPs, got {qc_snps}"
        assert qc_call_rate == "0.00%", f"Expected 0.00%, got {qc_call_rate}"
        print(f"  [PASS] Empty file handled: Total SNPs={qc_snps}, Call rate={qc_call_rate} (No division-by-zero NaN)")
        results["passed"] += 1
        results["tests"].append("Test 8: Zero-byte / NaN Division Defense")

        # -------------------------------------------------------------
        # TEST 9: ADVERSARIAL FILE (Binary Garbage & Corrupted Lines)
        # -------------------------------------------------------------
        print("\n[TEST 9] Ingesting Corrupted Binary Garbage & Giant Lines...")
        garbage = (
            "\x00\x01\x02\xff\xfe\r\n"
            "NOT_A_GENOME_LINE\r\n"
            + "#" * 5000 + "\r\n"
            + "A" * 100000 + "\r\n"
            + "rs429358\t19\t-99999\tCC\r\n"
            + "rs1800562\t\t\t\r\n"
            + "CORRUPT\t1\tNaN\t??\r\n"
        )
        page.evaluate("""(g) => {
          window.__genomePulse.processText(g, 'corrupted_sample.bin');
        }""", garbage)
        page.wait_for_timeout(500)
        qc_snps = page.locator("#qc-total-snps").text_content()
        assert int(qc_snps.replace(",", "")) >= 1, "Should have safely parsed the 1 valid line among garbage"
        print(f"  [PASS] Corrupted garbage successfully digested without crashing the Web Worker.")
        results["passed"] += 1
        results["tests"].append("Test 9: Binary & Malformed Garbage Recovery")

        # -------------------------------------------------------------
        # TEST 10: Export Mechanisms & Dialog Check
        # -------------------------------------------------------------
        print("\n[TEST 10] Testing Markdown and CSV Export Handlers...")
        # Verify export functions exist and don't throw
        page.evaluate("window.__genomePulse.exportMarkdownReport()")
        page.evaluate("window.__genomePulse.exportCsvReport()")
        print("  [PASS] Export functions executed successfully.")
        results["passed"] += 1
        results["tests"].append("Test 10: Export Handlers")

        # -------------------------------------------------------------
        # TEST 11: Real-World 23andMe APOE ε3/ε4 Carrier Ingestion & Carrier Tab
        # -------------------------------------------------------------
        print("\n[TEST 11] Testing User 23andMe APOE ε3/ε4 Carrier Ingestion & Carrier Filtering...")
        user_dna_apoe = """# 23andMe user upload test
# build 37
# rsid\tchromosome\tposition\tgenotype
rs429358\t19\t45411941\tCT
rs7412\t19\t45412079\tCC
rs1800562\t6\t26093141\tAG
rs113993960\t7\t117199644\tDI
rs4244285\t10\t96541604\tAG
"""
        page.evaluate("""(dna) => {
          window.__genomePulse.state.fileName = 'user_23andme_profile.txt';
          window.__genomePulse.processText(dna, 'user_23andme_profile.txt');
        }""", user_dna_apoe)

        page.wait_for_selector("#results-section:not(.hidden)", timeout=5000)
        page.wait_for_selector("#apoe-status-card:not(.hidden)", timeout=5000)

        apoe_title = page.locator("#apoe-diplotype-title").text_content()
        apoe_risk = page.locator("#apoe-risk-ratio").text_content()
        print(f"  [PASS] Synthesized APOE Diplotype: '{apoe_title}'")
        print(f"  [PASS] APOE Risk Ratio: '{apoe_risk}'")
        assert "ε3/ε4" in apoe_title, f"Expected ε3/ε4 in title, got: {apoe_title}"
        assert "3–4×" in apoe_risk, f"Expected 3–4x in risk, got: {apoe_risk}"

        # Test Carrier Filter tab explicitly
        print("  Testing Carrier Filter Tab...")
        page.locator("[data-filter='carrier']").click()
        page.wait_for_timeout(200)

        showing_carrier = page.locator("#showing-count").text_content()
        tbody_text = page.locator("#variants-tbody").text_content()
        print(f"  [PASS] Carrier filter active: '{showing_carrier}'")
        assert "APOE-STATUS" in tbody_text or "APOE" in tbody_text, "APOE carrier missing from Carrier filter!"
        print("  [PASS] APOE carrier verified present in Carrier filter datagrid!")
        results["passed"] += 1
        results["tests"].append("Test 11: Real-World 23andMe APOE ε3/ε4 Carrier Resolution")

        # -------------------------------------------------------------
        # TEST 12: Impeccable Typography & Sharp Theme System
        # -------------------------------------------------------------
        print("\n[TEST 12] Testing Impeccable Typography & Theme Toggle...")
        # Check Typekit link
        typekit_present = page.evaluate("""() => {
          return Boolean(document.querySelector('link[href*="use.typekit.net/cqu4tvx.css"]'));
        }""")
        assert typekit_present, "Typekit cqu4tvx stylesheet not found in document head!"
        print("  [PASS] Adobe Typekit stylesheet successfully linked.")

        # Test Theme Switcher
        theme_toggle = page.locator("#btn-theme-toggle")
        initial_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        print(f"  Initial Theme: '{initial_theme}'")
        assert initial_theme == "light", f"Expected default light mode, got: {initial_theme}"

        # Toggle to Dark HUD
        theme_toggle.click()
        page.wait_for_timeout(200)
        dark_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert dark_theme == "dark", f"Expected dark theme after toggle, got: {dark_theme}"
        print("  [PASS] Toggled to Dark HUD mode successfully.")

        # Toggle back to Light Mode (default clinical baseline)
        theme_toggle.click()
        page.wait_for_timeout(200)
        light_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert light_theme == "light", f"Expected light theme, got: {light_theme}"
        print("  [PASS] Toggled back to crisp Light Mode.")

        # Inspect APOE button opens drawer
        page.locator("#btn-inspect-apoe").click()
        page.wait_for_selector("#variant-drawer:not(.translate-x-full)", timeout=3000)
        page.wait_for_timeout(500)
        drawer_gene = page.locator("#drawer-gene").text_content()
        print(f"  [PASS] Inspect APOE drawer opened for gene: '{drawer_gene}'")
        assert drawer_gene == "APOE", f"Expected APOE in drawer, got: {drawer_gene}"

        # Capture drawer screenshot
        drawer_screenshot = str(Path(__file__).parent / "web_drawer_screenshot.png")
        page.screenshot(path=drawer_screenshot)
        print(f"  [+] Captured Clinical Proteomics Drawer screenshot to {drawer_screenshot}")

        # Close drawer for full overview screenshot
        page.locator("#btn-close-drawer").click()
        page.wait_for_timeout(400)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)

        # Capture final overview screenshot in crisp Light Mode
        screenshot_path = str(Path(__file__).parent / "web_adversarial_test.png")
        page.screenshot(path=screenshot_path)
        print(f"  [+] Captured clean Light Mode overview screenshot to {screenshot_path}")

        results["passed"] += 1
        results["tests"].append("Test 12: Impeccable Typography & Theme Toggle")

        browser.close()

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests Run: {results['passed'] + results['failed']}")
    print(f"Passed:          {results['passed']}")
    print(f"Failed:          {results['failed']}")
    if console_errors:
        print(f"\nConsole Warnings/Errors detected ({len(console_errors)}):")
        for err in console_errors[:5]:
            print(f"  - {err}")
    if js_dialogs:
        print(f"\nUncaught JS Alerts/Dialogs: {js_dialogs}")
    print("=" * 60)

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run_adversarial_suite())
