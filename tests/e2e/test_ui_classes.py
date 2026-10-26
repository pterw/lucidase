"""Drawer note, badge classes and the APOE e1/e4 page (S2b-C-1, C-5, C-11; S1c-C-1 page test).

Each badge is styled by an explicit map: an unknown or neutral value never borrows the not-detected (green) look or
a specific tier's look, and no gene-specific wording is hard-coded in the page. With the design system every KB
category has its own tone (Trait has the trait tone) and every evidence tier shares the one neutral tone.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from conftest import DEMO_FILE, apoe_row, goto_ready, open_apoe, show_table, wait_drawer_open

FIXTURES = Path(__file__).parent / "fixtures"
E1_E4 = FIXTURES / "apoe-atypical-23andme.txt"  # rs429358 C/C with rs7412 C/T: an e1/e4 genotype
NEUTRAL_TAG = "lds-tag-neutral"  # the one neutral tone (app.js NEUTRAL_TAG)
NOT_DETECTED_TAG = "lds-tag-cat-not-detected"  # the green tone, for the KB "Not detected" category only


def _row(page, rsid):
    return page.locator("#variants-tbody tr", has=page.locator(f"td:first-child:text-is('{rsid}')"))


def test_drawer_has_no_cyp2c19_note_for_a_vkorc1_drug_response(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)
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
    show_table(page)
    # MTHFR rs1801133 is a Trait interpretation in the KB. Its evidence is unclear, so it is under the Unclear tab.
    page.locator("[data-filter='insufficient']").click()
    badge = _row(page, "rs1801133").locator("span.lds-tag", has_text="Trait").first
    expect(badge).to_be_visible()
    classes = badge.get_attribute("class")
    assert NOT_DETECTED_TAG not in classes, classes
    assert "lds-tag-cat-trait" in classes, classes


def test_disagreeing_apoe_component_tiers_do_not_wear_the_tier_d_class(page):
    def tampered_kb(route):
        kb = json.loads(route.fetch().text())
        kb["loci"]["rs7412"]["evidence_tier"] = "Tier C"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(kb))

    page.route("**/knowledge-base.json", tampered_kb)
    goto_ready(page, page.base_url)
    page.set_input_files("#file-input", str(DEMO_FILE))
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)
    cell = page.locator("#variants-tbody tr").first.locator("span.lds-tag", has_text="rs7412: Tier C")
    expect(cell).to_be_visible()
    classes = cell.get_attribute("class").split()
    assert NEUTRAL_TAG in classes, classes
    # No result or category tone on a tier label: only the neutral tone.
    assert not [c for c in classes if c.startswith(("lds-tag-state-", "lds-tag-cat-"))], classes


def test_apoe_e1_e4_page_shows_no_e4_inheritance_figure(loaded_page):
    page = loaded_page
    page.set_input_files("#file-input", str(E1_E4))
    expect(page.locator("#results-section")).to_be_visible()
    expect(apoe_row(page)).to_be_visible()
    assert page.evaluate("() => window.__lucidase.state.apoe.diplotype") == "atypical"
    open_apoe(page)
    elements = (
        "#drawer-seg-risk-unscreened",
        "#drawer-seg-risk-carrier",
        "#drawer-seg-carrier-prior",
        "#sim-p-affected",
        "#sim-p-carrier",
        "#sim-p-wildtype",
    )
    for element in elements:
        assert page.locator(element).inner_text().strip() == "Not available", element
    for row in ("affected", "carrier", "wildtype"):
        expect(page.locator(f"#sim-bar-{row}")).to_have_css("transform", "matrix(0, 0, 0, 1, 0, 0)")
    text = page.locator("#drawer-segregation-container").inner_text().lower()
    assert "inheriting the e4 allele" not in text, text


def _found_acmg_rows(page):
    """The Found checks that carry the ACMG pill. The table has no ACMG tab: the pill is on the row."""
    show_table(page)
    page.locator("[data-filter='observed']").click()
    return page.locator("#variants-tbody tr", has=page.locator("span.lds-tag-accent", has_text="ACMG"))


def _report_row(page, rsid):
    return page.locator(f'#report-groups article.lds-finding[data-finding-id="{rsid}"]')


def test_two_found_variants_of_one_acmg_gene_are_two_rows_of_one_group(page):
    # The demo carries HFE C282Y (rs1800562) and H63D (rs1799945), both heterozygous. H63D's evidence is unclear in the
    # KB; with it marked sufficient here, both are Found: two variants, one gene.
    def tampered_kb(route):
        kb = json.loads(route.fetch().text())
        kb["loci"]["rs1799945"]["evidence_sufficiency"] = "sufficient"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(kb))

    page.route("**/knowledge-base.json", tampered_kb)
    goto_ready(page, page.base_url)
    page.set_input_files("#file-input", str(DEMO_FILE))
    expect(page.locator("#results-section")).to_be_visible()
    rows = _found_acmg_rows(page)
    expect(rows).to_have_count(2)
    for rsid in ("rs1800562", "rs1799945"):
        expect(_row(page, rsid).locator(".lds-tag-state-supported_and_observed")).to_have_text("Found")
        expect(_report_row(page, rsid).locator(":scope > span.lds-mark-supported_and_observed")).to_have_count(1)
    # One gene, so the two Found checks sit in the same report group, one row each.
    groups = {_report_row(page, rsid).evaluate("el => el.closest('section').id") for rsid in ("rs1800562", "rs1799945")}
    assert len(groups) == 1, groups


def test_an_unclear_acmg_variant_is_not_listed_as_found(loaded_page):
    page = loaded_page
    page.set_input_files("#file-input", str(DEMO_FILE))
    expect(page.locator("#results-section")).to_be_visible()
    # Unmodified KB: H63D is Unclear, so the Found tab lists only C282Y among the checks with the ACMG pill.
    rows = _found_acmg_rows(page)
    expect(rows).to_have_count(1)
    expect(_row(page, "rs1800562")).to_have_count(1)
    expect(_row(page, "rs1799945")).to_have_count(0)
    # The report shows C282Y as Found and H63D as Unclear (a row, but not a finding).
    expect(_report_row(page, "rs1800562").locator(":scope > span.lds-mark-supported_and_observed")).to_have_count(1)
    expect(_report_row(page, "rs1799945").locator(":scope > span.lds-mark-insufficient_evidence")).to_have_count(1)
    page.locator("[data-filter='insufficient']").click()
    expect(_row(page, "rs1799945")).to_have_count(1)
    expect(_row(page, "rs1799945").locator(".lds-tag-state-insufficient_evidence")).to_have_text("Unclear")
    expect(_row(page, "rs1799945").locator("span.lds-tag-accent", has_text="ACMG")).to_have_count(1)
