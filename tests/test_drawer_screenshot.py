from __future__ import annotations
import http.server
import threading
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
PORT = 8766

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)
    def log_message(self, format, *args):
        pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), QuietHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}", wait_until="networkidle")
    
    # Click demo button
    page.locator("#btn-load-demo").click()
    page.wait_for_selector("#results-section:not(.hidden)", timeout=5000)
    
    # Click first variant row (DPYD or APOE) to open drawer
    page.locator("#variants-tbody tr").first.click()
    page.wait_for_selector("#variant-drawer:not(.translate-x-full)", timeout=3000)
    page.wait_for_timeout(300)
    
    screenshot_path = str(Path(__file__).parent / "web_drawer_screenshot.png")
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"Captured drawer screenshot to {screenshot_path}")
    browser.close()
