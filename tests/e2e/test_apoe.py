"""APOE diplotype from allele counts with explicit indeterminate states (P1-025).

The diplotype is asserted only when both component loci resolve. An atypical combination or a missing component is
shown as indeterminate, never as a normal baseline.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect

FIXTURES = Path(__file__).parent / "fixtures"
ATYPICAL = FIXTURES / "apoe-atypical-23andme.txt"
ONLY_E4_SNP = FIXTURES / "apoe-only-rs429358-23andme.txt"
E3E4 = FIXTURES / "apoe-e3e4-23andme.txt"


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible()
    expect(page.locator("#apoe-status-card")).to_be_visible()


def _apoe(page):
    return page.evaluate("() => window.__lucidase.state.apoe")


def _apoe_rows(page):
    return page.evaluate(
        "() => ['records','negativeChecks','arrayGaps','insufficientEvidence']"
        ".flatMap(g => window.__lucidase.state[g]).filter(r => r.gene === 'APOE').length"
    )


def test_atypical_combination_is_indeterminate_not_normal(loaded_page):
    _analyse(loaded_page, ATYPICAL)
    card = loaded_page.locator("#apoe-status-card")
    text = card.inner_text()
    assert "requires an e1-type haplotype" in text
    assert "cannot be resolved from genotype array data" in text
    assert "tested normal" not in text.lower()
    assert "ε3/ε3" not in text
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
    text = loaded_page.locator("#apoe-status-card").inner_text()
    assert "Not on your chip" in text
    assert "ε" not in text
    assert _apoe_rows(loaded_page) == 1


def test_demo_still_shows_e4_e4(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#apoe-status-card")).to_be_visible()
    expect(loaded_page.locator("#apoe-diplotype-title")).to_contain_text("ε4/ε4")
    assert _apoe(loaded_page)["coverage_state"] == "supported_and_observed"


def test_apoe_numbers_come_from_the_knowledge_base(loaded_page):
    _analyse(loaded_page, E3E4)
    apoe = _apoe(loaded_page)
    kb_interp = loaded_page.evaluate(
        "async () => (await (await fetch('./src/knowledge-base.json')).json()).genes.APOE.diplotypes['e3/e4']"
    )
    assert apoe["magnitude"] == kb_interp["magnitude"]
    note = " [Figures: manually curated; source citation pending verification]"
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
