"""HFE drawer: offspring simulator and biotools panel (converted from the former
uncollected tests/test_segregation_and_biotools_e2e.py script).

Dropped on conversion because they encoded behaviour listed as wrong in
findings.md: the "2 multi-locus findings" count and the "trans phase compound
heterozygote" card text (P1-026: asserts phase on unphased data).
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from conftest import wait_drawer_open


KB_PATH = Path(__file__).resolve().parents[2] / "web" / "src" / "knowledge-base.json"


def _hfe_imported_vep(rsid):
    """The VEP evidence the pipeline imported for one HFE locus (the drawer must show this, not a literal)."""
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    locus = kb["loci"][rsid]
    assert locus["gene"] == "HFE"
    return locus["evidence"]["vep"]


def _open_hfe_drawer(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    page.locator("button.btn-inspect-gene[data-gene='HFE']").first.click()
    wait_drawer_open(page)


def test_hfe_offspring_simulator(loaded_page):
    _open_hfe_drawer(loaded_page)
    assert "HFE" in loaded_page.locator("#drawer-gene").inner_text()
    seg_mode = loaded_page.locator("#drawer-seg-mode-badge").inner_text().lower()
    assert "autosomal recessive" in seg_mode
    expected = {"carrier": "25%", "affected": "50%", "wildtype": "0%"}
    for partner, risk in expected.items():
        loaded_page.locator(f".partner-sim-btn[data-partner='{partner}']").click()
        expect(loaded_page.locator("#sim-p-affected")).to_have_text(risk)


def test_hfe_biotools_panel(loaded_page, tmp_path):
    _open_hfe_drawer(loaded_page)
    page = loaded_page
    assert "P55899" in page.locator("#drawer-af-uniprot").inner_text()
    assert float(page.locator("#drawer-af-plddt").inner_text()) >= 80.0
    imported = _hfe_imported_vep("rs1800562")
    assert imported["mane_select_ensembl"] in page.locator("#drawer-ens-transcript").inner_text()
    am_text = page.locator("#drawer-ens-alphamissense").inner_text()
    assert imported["alphamissense_class"] in am_text
    assert f"{imported['alphamissense_score']:.2f}" in am_text
    assert "liver" in page.locator("#drawer-encode-tissues").inner_text().lower()
    # The docked Inspector scrolls its body, not the whole pane.
    page.locator("#variant-drawer .lds-inspector-body").evaluate("el => el.scrollTop = 450")
    shot = tmp_path / "biotools.png"
    page.screenshot(path=str(shot))
    assert shot.stat().st_size > 0
