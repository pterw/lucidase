"""Classification by alt-allele count from the pipeline knowledge base (P0-006, P0-007, P1-022, P1-024).

Observed findings are the default results table (`state.records`). A wild-type result must
never appear there; it is a supported-not-observed (or insufficient-evidence) record instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, goto_ready, show_table

FIXTURES = Path(__file__).parent / "fixtures"
WILDTYPE = FIXTURES / "wildtype-23andme.txt"


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible()


def _rsids(page, group):
    return page.evaluate(f"() => window.__lucidase.state.{group}.map(r => r.rsid)")


def _row_for(page, rsid):
    return page.locator("#variants-tbody tr", has=page.locator(f"td:first-child:text-is('{rsid}')"))


def test_wildtype_loci_are_not_observed_findings(loaded_page):
    _analyse(loaded_page, WILDTYPE)
    observed = _rsids(loaded_page, "records")
    # HFE H63D, VKORC1, SLCO1B1 and CYP2C19 have no alt allele in this file.
    for rsid in ("rs1799945", "rs9923231", "rs4149056", "rs4244285"):
        assert rsid not in observed, f"{rsid} is wild-type or untested but listed as an observed finding"
    for rsid in ("rs1799945", "rs9923231", "rs4149056"):
        expect(_row_for(loaded_page, rsid)).to_have_count(0)


def test_wildtype_coverage_states_are_supported_not_observed(loaded_page):
    _analyse(loaded_page, WILDTYPE)
    negatives = loaded_page.evaluate(
        "() => Object.fromEntries(window.__lucidase.state.negativeChecks.map(r => [r.rsid, r.coverage_state]))"
    )
    for rsid in ("rs9923231", "rs4149056"):
        assert negatives.get(rsid) == "supported_not_observed", negatives
    # H63D has insufficient evidence (Tier D): wild-type there is reported as insufficient_evidence.
    insufficient = loaded_page.evaluate(
        "() => Object.fromEntries(window.__lucidase.state.insufficientEvidence.map(r => [r.rsid, r.sample_observation]))"
    )
    assert insufficient.get("rs1799945") == "wild_type", insufficient
    gaps = _rsids(loaded_page, "arrayGaps")
    assert "rs4244285" in gaps and "rs6025" in gaps  # absent from the file / a no-call


def test_each_locus_is_counted_in_exactly_one_state(loaded_page):
    _analyse(loaded_page, WILDTYPE)
    counts = loaded_page.evaluate(
        "() => { const c = window.__lucidase.state.coverageSummary; "
        "return [c.supported_and_observed_count, c.supported_not_observed_count, "
        "c.not_tested_by_array_count, c.insufficient_evidence_count, c.total_loci]; }"
    )
    assert sum(counts[:4]) == counts[4], counts


def test_demo_mthfr_het_is_an_observed_finding(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    assert "rs1801133" in _rsids(loaded_page, "records")
    assert "rs1801133" not in _rsids(loaded_page, "negativeChecks")
    row = _row_for(loaded_page, "rs1801133")
    expect(row).to_have_count(1)
    assert "tested wt" not in row.inner_text().lower()
    assert "tested normal" not in row.inner_text().lower()
    state = loaded_page.evaluate("() => window.__lucidase.state.records.find(r => r.rsid === 'rs1801133').coverage_state")
    expect(row.locator(f".lds-tag-state-{state}")).to_have_text(PLAIN_WORDS[state])


# The design system's plain result words (components/core/hooks.js stateMeta), verbatim.
PLAIN_WORDS = {
    "supported_and_observed": "Found",
    "supported_not_observed": "Not found",
    "not_tested_by_array": "Not on your chip",
    "outside_coverage": "Not checked",
    "insufficient_evidence": "Unclear",
}
OLD_WORDS = ("Supported", "Observed", "Tested WT", "Array Gap", "Wild-Type", "Conflicting", "Not on the chip", "State 1",
             "State 2", "State 3", "State 4", "State 5", "★", "☆")


def test_results_read_in_the_plain_words(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    # Summary counts: the word beside each state's mark.
    for state, word in PLAIN_WORDS.items():
        expect(page.locator(f".lds-count-label:has(.lds-mark-{state})")).to_have_text(word)
    # Filter tabs for the per-state tables.
    show_table(page)
    for name, word in (("all", "Found"), ("negative", "Not found"), ("gaps", "Not on your chip"), ("insufficient", "Unclear")):
        expect(page.locator(f"[data-filter='{name}']")).to_have_text(word)
    # Table badges under each state filter.
    for name in ("all", "negative", "gaps", "insufficient"):
        page.locator(f"[data-filter='{name}']").click()
        for state, word in PLAIN_WORDS.items():
            tags = page.locator(f"#variants-tbody .lds-tag-state-{state}")
            for i in range(tags.count()):
                expect(tags.nth(i)).to_have_text(word)
    page.locator("[data-filter='all']").click()
    page.locator("#variants-tbody tr", has=page.locator(".lds-tag-state-supported_and_observed")).first.click()
    expect(page.locator("#drawer-coverage-state-badge")).to_have_text("Found")
    expect(page.locator("#drawer-stars")).to_have_text(re.compile(r"\d of 4 review stars|No ClinVar review status"))
    text = page.locator("body").inner_text()
    for old in OLD_WORDS:
        assert old not in text, old


def test_apoe_components_are_not_separate_finding_rows(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    for rsid in ("rs429358", "rs7412"):
        expect(_row_for(loaded_page, rsid)).to_have_count(0)
        assert rsid not in _rsids(loaded_page, "records")
    # The combined APOE finding is still shown.
    expect(loaded_page.locator("#apoe-status-card")).to_be_visible()


@pytest.mark.allow_console_errors
def test_knowledge_base_fetch_failure_is_visible(page):
    page.route(
        "**/knowledge-base.json",
        lambda route: route.fulfill(status=500, content_type="application/json", body="{}"),
    )
    goto_ready(page, page.base_url)
    expect(page.locator("#analysis-error")).to_be_hidden()
    page.set_input_files("#file-input", str(DEMO_FILE))
    expect(page.locator("#analysis-error")).to_be_visible()
    expect(page.locator("#results-section")).to_be_hidden()
    expect(page.locator("#progress-section")).to_be_hidden()
