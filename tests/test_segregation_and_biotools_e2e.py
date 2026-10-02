from __future__ import annotations
import http.server
import threading
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
PORT = 8788

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)
    def log_message(self, format, *args):
        pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), QuietHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
print(f"Started web server on port {PORT}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.on("dialog", lambda dialog: print(f"DIALOG ALERT: {dialog.message}") or dialog.accept())
    page.on("requestfailed", lambda req: print(f"REQUEST FAILED: {req.url} {req.failure}"))
    page.on("response", lambda res: print(f"RESPONSE: {res.url} {res.status}"))
    page.goto(f"http://127.0.0.1:{PORT}", wait_until="networkidle")

    # Step 1: Click Load Demo button
    print("1. Loading demo 23andMe sample...")
    btn_demo = page.locator("#btn-load-demo")
    print("   Clicking #btn-load-demo via playwright locator...")
    btn_demo.click()
    page.wait_for_selector("#results-section:not(.hidden)", timeout=10000)
    print("   Results section appeared.")

    # Step 2: Validate Multi-Locus Segregation & Assortment Section
    print("2. Verifying Multi-Locus Assortment section...")
    page.wait_for_selector("#assortment-section:not(.hidden)", timeout=3000)
    badge_text = page.locator("#assortment-findings-count-badge").inner_text()
    print(f"   Badge: {badge_text}")
    assert "2 multi-locus finding" in badge_text.lower(), f"Expected 2 findings, got {badge_text}"

    cards = page.locator("#assortment-cards-container > div")
    card_count = cards.count()
    print(f"   Found {card_count} multi-locus cards.")
    assert card_count == 2, f"Expected 2 cards, got {card_count}"

    card1_text = cards.nth(0).inner_text()
    card2_text = cards.nth(1).inner_text()
    print("   Card 1 text:", repr(card1_text))
    print("   Card 2 text:", repr(card2_text))
    assert "trans phase compound heterozygote" in card1_text.lower() or "trans phase compound heterozygote" in card2_text.lower()
    assert "mendel's 2nd law" in card1_text.lower() or "mendel's 2nd law" in card2_text.lower()
    print("   Verified HFE compound heterozygote and F5+F2 independent assortment cards.")

    # Capture dashboard screenshot showing APOE and Multi-Locus sections
    dash_shot = str(Path(__file__).parent / "web_assortment_dashboard.png")
    page.screenshot(path=dash_shot, full_page=False)
    print(f"   Captured dashboard screenshot to {dash_shot}")

    # Step 3: Open drawer for an autosomal recessive carrier (e.g., HFE)
    print("3. Inspecting HFE locus in drawer...")
    # Click inspect HFE from the assortment card button
    hfe_inspect_btn = page.locator("button.btn-inspect-gene[data-gene='HFE']").first
    hfe_inspect_btn.click()
    page.wait_for_selector("#variant-drawer:not(.translate-x-full)", timeout=3000)
    page.wait_for_timeout(400)

    # Verify Segregation Box
    drawer_gene = page.locator("#drawer-gene").inner_text()
    seg_mode = page.locator("#drawer-seg-mode-badge").inner_text()
    print(f"   Drawer Gene: {drawer_gene}, Mode: {seg_mode}")
    assert "HFE" in drawer_gene
    assert "autosomal recessive" in seg_mode.lower()

    # Test Interactive Offspring Risk Simulator
    print("4. Testing Interactive Offspring Risk Simulator...")
    sim_aff_initial = page.locator("#sim-p-affected").inner_text()
    print(f"   Unscreened partner initial risk: {sim_aff_initial}")

    # Click Carrier partner button
    page.locator(".partner-sim-btn[data-partner='carrier']").click()
    page.wait_for_timeout(200)
    carrier_risk = page.locator("#sim-p-affected").inner_text()
    print(f"   Carrier partner risk: {carrier_risk}")
    assert carrier_risk == "25%", f"Expected 25%, got {carrier_risk}"

    # Click Affected partner button
    page.locator(".partner-sim-btn[data-partner='affected']").click()
    page.wait_for_timeout(200)
    affected_risk = page.locator("#sim-p-affected").inner_text()
    print(f"   Affected partner risk: {affected_risk}")
    assert affected_risk == "50%", f"Expected 50%, got {affected_risk}"

    # Click Wild-Type partner button
    page.locator(".partner-sim-btn[data-partner='wildtype']").click()
    page.wait_for_timeout(200)
    wildtype_risk = page.locator("#sim-p-affected").inner_text()
    print(f"   Wildtype partner risk: {wildtype_risk}")
    assert wildtype_risk == "0%", f"Expected 0%, got {wildtype_risk}"

    # Step 5: Verify Biotools Multi-Source Insights
    print("5. Verifying Deep Biotools Insights Panel...")
    af_uniprot = page.locator("#drawer-af-uniprot").inner_text()
    af_plddt = page.locator("#drawer-af-plddt").inner_text()
    ens_transcript = page.locator("#drawer-ens-transcript").inner_text()
    ens_am = page.locator("#drawer-ens-alphamissense").inner_text()
    ens_loeuf = page.locator("#drawer-ens-loeuf").inner_text()
    encode_tissues = page.locator("#drawer-encode-tissues").inner_text()

    print(f"   AlphaFold DB: {af_uniprot}, pLDDT={af_plddt}")
    print(f"   Ensembl VEP: {ens_transcript}, AlphaMissense={ens_am}, LOEUF={ens_loeuf}")
    print(f"   ENCODE Tissues: {encode_tissues[:60]}...")

    assert "P55899" in af_uniprot
    assert float(af_plddt) >= 80.0
    assert "MANE Select" in ens_transcript
    assert "likely_pathogenic" in ens_am
    assert "liver" in encode_tissues.lower()

    # Step 6: Capture screenshot of drawer with Segregation & Biotools
    drawer_shot = str(Path(__file__).parent / "web_drawer_segregation_biotools.png")
    page.screenshot(path=drawer_shot, full_page=False)
    print(f"   Captured drawer top screenshot to {drawer_shot}")

    # Scroll drawer down to show Deep Biotools panel completely
    page.locator("#variant-drawer").evaluate("el => el.scrollTop = 450")
    page.wait_for_timeout(300)
    biotools_shot = str(Path(__file__).parent / "web_drawer_biotools_scrolled.png")
    page.screenshot(path=biotools_shot, full_page=False)
    print(f"   Captured scrolled biotools screenshot to {biotools_shot}")

    browser.close()
    print("\nAll E2E segregation and biotools assertions passed successfully!")
