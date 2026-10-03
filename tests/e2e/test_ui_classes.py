"""Drawer note, badge classes and the APOE e1/e4 page (S2b-C-1, C-5, C-11; S1c-C-1 page test).

Each badge is styled by an explicit map: an unknown or neutral value never borrows the benign (green) or Tier D look,
and no gene-specific wording is hard-coded in the page.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from conftest import DEMO_FILE, goto_ready, wait_drawer_open

FIXTURES = Path(__file__).parent / "fixtures"
E1_E4 = FIXTURES / "apoe-atypical-23andme.txt"  # rs429358 C/C with rs7412 C/T: an e1/e4 genotype
TIER_D_TEXT_CLASS = "text-slate-700"  # the Tier D badge's own text colour; the neutral class uses text-slate-800


def _row(page, rsid):
    return page.locator("#variants-tbody tr", has=page.locator(f"td:first-child:text-is('{rsid}')"))


def test_drawer_has_no_cyp2c19_note_for_a_vkorc1_drug_response(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    _row(page, "rs9923231").click()
    wait_drawer_open(page)
    expect(page.locator("#drawer-drug-box")).to_be_visible()
    text = page.locator("#drawer-drug-box").inner_text()
    assert "*17" not in text, text
    assert "metabolizer" not in text.lower(), text


def test_trait_category_is_not_styled_benign(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    # MTHFR rs1801133 is a Trait interpretation in the KB.
    badge = _row(page, "rs1801133").locator("span", has_text="Trait").first
    expect(badge).to_be_visible()
    classes = badge.get_attribute("class")
    assert "badge-benign" not in classes, classes
    assert "text-slate-800" in classes, classes


def test_disagreeing_apoe_component_tiers_do_not_wear_the_tier_d_class(page):
    def tampered_kb(route):
        kb = json.loads(route.fetch().text())
        kb["loci"]["rs7412"]["evidence_tier"] = "Tier C"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(kb))

    page.route("**/knowledge-base.json", tampered_kb)
    goto_ready(page, page.base_url)
    page.set_input_files("#file-input", str(DEMO_FILE))
    expect(page.locator("#results-section")).to_be_visible()
    cell = page.locator("#variants-tbody tr").first.locator("span.font-mono", has_text="rs7412: Tier C")
    expect(cell).to_be_visible()
    classes = cell.get_attribute("class")
    assert TIER_D_TEXT_CLASS not in classes, classes
    assert "text-slate-800" in classes, classes


def test_apoe_e1_e4_page_shows_no_e4_inheritance_figure(loaded_page):
    page = loaded_page
    page.set_input_files("#file-input", str(E1_E4))
    expect(page.locator("#results-section")).to_be_visible()
    expect(page.locator("#apoe-status-card")).to_be_visible()
    assert page.evaluate("() => window.__lucidase.state.apoe.diplotype") == "atypical"
    page.locator("#btn-inspect-apoe").click()
    wait_drawer_open(page)
    for element in ("#drawer-seg-risk-unscreened", "#drawer-seg-risk-carrier", "#drawer-seg-carrier-prior"):
        assert page.locator(element).inner_text().strip() == "Not available", element
    text = page.locator("#drawer-segregation-container").inner_text().lower()
    assert "inherits the e4 allele" not in text, text


def test_two_variants_of_one_acmg_gene_count_as_one_actionable_gene(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    # The demo carries HFE C282Y (rs1800562) and H63D (rs1799945), both heterozygous: two variants, one gene.
    page.locator("[data-filter='acmg']").click()
    expect(page.locator("#variants-tbody tr")).to_have_count(2)
    expect(page.locator("#count-acmg")).to_have_text("1")
