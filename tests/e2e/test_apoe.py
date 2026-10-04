"""APOE diplotype from allele counts with explicit indeterminate states (P1-025).

The diplotype is asserted only when both component loci resolve. An atypical combination or a missing component is
shown as indeterminate, never as a normal baseline.

APOE is one FindingRow in the grouped report; its details (the Ligature, the KB risk figures with their curation label,
the protein abundance) open in the Inspector (design system ui_kits/web/AnalysisScreen.jsx, RecordInspector.jsx).
There is no separate APOE card.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from conftest import WEB_DIR, apoe_row, open_apoe

FIXTURES = Path(__file__).parent / "fixtures"
ATYPICAL = FIXTURES / "apoe-atypical-23andme.txt"
ONLY_E4_SNP = FIXTURES / "apoe-only-rs429358-23andme.txt"
E3E4 = FIXTURES / "apoe-e3e4-23andme.txt"

# The owner's pending decision (cite or remove the APOE figures): until then each figure carries this label, word for word.
FIGURES_NOTE = "manually curated; source citation pending verification"
INSPECTOR = "#variant-drawer"
LIST = "#results-section .lds-results-main"
LIGATURE_RESULT = f"{INSPECTOR} figure.lds-ligature .lds-ligature-result"
RISK_RATIO = "#drawer-apoe-risk-ratio"
LIFETIME = "#drawer-apoe-lifetime"


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible()
    expect(apoe_row(page)).to_be_visible()


def _apoe(page):
    return page.evaluate("() => window.__lucidase.state.apoe")


def _apoe_rows(page):
    return page.evaluate(
        "() => ['records','negativeChecks','arrayGaps','insufficientEvidence']"
        ".flatMap(g => window.__lucidase.state[g]).filter(r => r.gene === 'APOE').length"
    )


def _kb():
    return json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))


def _kb_figure(diplotype, prefix):
    """A KB risk figure for a diplotype (its caveat line without the prefix), as the card showed it, with the label."""
    caveats = _kb()["genes"]["APOE"]["diplotypes"][diplotype]["caveats"]
    (line,) = [c for c in caveats if c.startswith(prefix)]
    return f"{line[len(prefix):]} ({FIGURES_NOTE})"


def test_atypical_combination_is_indeterminate_not_normal(loaded_page):
    _analyse(loaded_page, ATYPICAL)
    inspector = open_apoe(loaded_page)
    text = inspector.inner_text()
    assert "requires an e1-type haplotype" in text
    assert "cannot be resolved from genotype array data" in text
    assert "tested normal" not in text.lower()
    assert "ε3/ε3" not in text
    # No diplotype and no figures: each says "Not available"; the result word is Unclear.
    expect(loaded_page.locator(LIGATURE_RESULT)).to_have_text("Not available")
    expect(loaded_page.locator(RISK_RATIO)).to_have_text("Not available")
    expect(loaded_page.locator(LIFETIME)).to_have_text("Not available")
    expect(loaded_page.locator("#drawer-coverage-state-badge")).to_have_text("Unclear")
    apoe = _apoe(loaded_page)
    assert apoe["coverage_state"] == "insufficient_evidence"
    assert apoe["sample_observation"] == "variant_present"
    assert apoe["diplotype"] == "atypical"
    assert _apoe_rows(loaded_page) == 1


def test_single_component_is_not_tested_with_no_diplotype(loaded_page):
    _analyse(loaded_page, ONLY_E4_SNP)
    apoe = _apoe(loaded_page)
    assert apoe["diplotype"] is None
    assert apoe["coverage_state"] == "not_tested_by_array"
    assert "rs7412" in apoe["reason"]
    text = open_apoe(loaded_page).inner_text()
    assert "Not on your chip" in text
    assert "ε" not in text
    expect(loaded_page.locator(LIGATURE_RESULT)).to_have_text("Not available")
    expect(loaded_page.locator(RISK_RATIO)).to_have_text("Not available")
    expect(loaded_page.locator(LIFETIME)).to_have_text("Not available")
    assert _apoe_rows(loaded_page) == 1


def test_demo_still_shows_e4_e4(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(apoe_row(loaded_page)).to_be_visible()
    open_apoe(loaded_page)
    expect(loaded_page.locator(LIGATURE_RESULT)).to_have_text("APOE ε4/ε4")
    assert _apoe(loaded_page)["coverage_state"] == "supported_and_observed"


def test_the_apoe_card_is_folded_into_the_apoe_row_and_inspector(loaded_page):
    """No standalone APOE card; every fact it showed is in the APOE row's Inspector, each once.

    Positive control for the absence: the APOE row exists, and the same facts (the same strings) are found in its
    Inspector. Expected values come from the page state and the KB.
    """
    page = loaded_page
    _analyse(page, E3E4)
    apoe = _apoe(page)
    assert apoe["diplotype"] == "e3/e4"
    expect(page.locator("#apoe-status-card")).to_have_count(0)
    expect(page.locator("#btn-inspect-apoe")).to_have_count(0)
    expect(page.locator("[id^='apoe-']")).to_have_count(0)

    row = apoe_row(page)
    expect(row).to_have_count(1)
    expect(row).to_be_visible()
    expect(row.locator(".lds-finding-gene")).to_have_text("APOE")

    risk_ratio = _kb_figure("e3/e4", "Relative risk: ")
    lifetime = _kb_figure("e3/e4", "Lifetime risk: ")
    # The card's risk figures are nowhere in the list column any more...
    list_text = page.locator(LIST).inner_text()
    assert risk_ratio not in list_text and lifetime not in list_text

    inspector = open_apoe(page)
    text = inspector.inner_text()
    # ...and each is in the Inspector, word for word with its label, exactly once.
    expect(page.locator(RISK_RATIO)).to_have_text(risk_ratio)
    expect(page.locator(LIFETIME)).to_have_text(lifetime)
    assert text.count(risk_ratio) == 1, text
    assert text.count(lifetime) == 1, text
    # The labels the card gave them.
    expect(page.locator(RISK_RATIO).locator("xpath=preceding-sibling::dt")).to_have_text("Risk ratio")
    expect(page.locator(LIFETIME).locator("xpath=preceding-sibling::dt")).to_have_text("Estimated lifetime risk")
    # Both sit in "What was found", after the Ligature.
    found = inspector.locator("section[aria-labelledby='isec-found']")
    expect(found.locator(RISK_RATIO)).to_have_count(1)
    assert found.locator("#drawer-ligature").evaluate(
        "(lig) => Boolean(lig.compareDocumentPosition(document.getElementById('drawer-apoe-risk-ratio'))"
        " & Node.DOCUMENT_POSITION_FOLLOWING)"
    )
    # The other KB caveats stay under "Caveats and scope" (the list is not emptied with the figures).
    others = [c for c in apoe["caveats"] if FIGURES_NOTE not in c]
    assert others, apoe["caveats"]
    expect(page.locator("#drawer-caveats-list li")).to_have_text(others)

    # Diplotype (the card's title), from the Ligature.
    expect(page.locator(LIGATURE_RESULT)).to_have_text(f"APOE {apoe['diplotypeDisplay']}")
    # The state word and the significance (the card's "Found · <significance>" tag).
    expect(page.locator("#drawer-coverage-state-badge")).to_have_text(apoe["stateLabel"])
    expect(page.locator("#drawer-significance")).to_have_text(apoe["significance"])
    # The phenotype text, with its figures label.
    assert apoe["phenotype"].endswith(f"[Figures: {FIGURES_NOTE}]")
    expect(page.locator("#drawer-phenotype")).to_contain_text(apoe["phenotype"])
    # The underlying genotypes, one per marker.
    expect(inspector.locator("figure.lds-ligature .lds-ligature-markers > span")).to_have_text(
        [f"{c['rsid']} {c['genotype_display']}" for c in apoe["components"]]
    )
    # Protein abundance (Human Protein Atlas): every tissue with its level.
    tissues = apoe["hpa_tissues"]
    assert tissues
    hpa_rows = page.locator("#drawer-hpa-tissues > div")
    expect(hpa_rows).to_have_count(len(tissues))
    for i, (tissue, level) in enumerate(tissues.items()):
        expect(hpa_rows.nth(i).locator("span").first).to_have_text(tissue, ignore_case=True)
        expect(hpa_rows.nth(i).locator("span.lds-tag")).to_have_text(level)


def test_apoe_numbers_come_from_the_knowledge_base(loaded_page):
    _analyse(loaded_page, E3E4)
    apoe = _apoe(loaded_page)
    kb_interp = loaded_page.evaluate(
        "async () => (await (await fetch('./src/knowledge-base.json')).json()).genes.APOE.diplotypes['e3/e4']"
    )
    assert apoe["magnitude"] == kb_interp["magnitude"]
    note = f" [Figures: {FIGURES_NOTE}]"
    assert apoe["phenotype"].startswith(kb_interp["phenotype"])
    assert apoe["phenotype"][len(kb_interp["phenotype"]):] == note
    # The composite row carries each component's own evidence, never one component's as its own.
    assert apoe["clinvar_stars"] is None
    kb_loci = loaded_page.evaluate(
        "async () => (await (await fetch('./src/knowledge-base.json')).json()).loci"
    )
    assert [c["rsid"] for c in apoe["componentEvidence"]] == ["rs429358", "rs7412"]
    assert [c["stars"] for c in apoe["componentEvidence"]] == [
        kb_loci[r]["evidence"]["clinvar"]["stars"] for r in ("rs429358", "rs7412")
    ]


def test_coverage_cards_count_apoe_once(loaded_page):
    _analyse(loaded_page, E3E4)
    counts = loaded_page.evaluate(
        "() => { const c = window.__lucidase.state.coverageSummary; "
        "return [c.supported_and_observed_count, c.supported_not_observed_count, "
        "c.not_tested_by_array_count, c.insufficient_evidence_count, c.total_loci]; }"
    )
    assert sum(counts[:4]) == counts[4], counts
    listed = loaded_page.evaluate(
        "() => ['records','negativeChecks','arrayGaps','insufficientEvidence']"
        ".reduce((n, g) => n + window.__lucidase.state[g].length, 0)"
    )
    assert listed == counts[4], (listed, counts)
