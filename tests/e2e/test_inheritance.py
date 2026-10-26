"""Genotype-aware inheritance in the web app (T8: P0-008, P1-026, P1-027).

The drawer simulator and the CSV export used to ignore the patient's genotype: a wild-type
F5 locus showed a 50% chance, an e4/e4 patient showed 50/0/50, and trait or risk-factor genes
used disease and recurrence wording.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from playwright.sync_api import expect

from conftest import DEMO_FILE, goto_ready, open_apoe, show_table, wait_drawer_open

WILDTYPE = Path(__file__).parent / "fixtures" / "wildtype-23andme.txt"
# Anything that says or implies a disease, a recurrence figure or a carrier status. A risk-factor, trait or
# pharmacogenomic locus gets allele-transmission words only (AGENTS.md 4.4).
FORBIDDEN_FOR_NON_MENDELIAN = ("affected", "recurrence", "disease", "carrier", "condition", "diagnos", "penetrance")


def _wildtype_f5_file(tmp_path):
    """The wild-type fixture with a called, homozygous-reference F5 Leiden genotype (minus strand GG)."""
    text = WILDTYPE.read_text(encoding="utf-8").replace("rs6025\t1\t169519049\t--", "rs6025\t1\t169519049\tGG")
    # One observed variant (MTHFR het) so the CSV export has a findings list to write.
    text = text.replace("rs1801133\t1\t11856378\tGG", "rs1801133\t1\t11856378\tAG")
    assert "rs6025\t1\t169519049\tGG" in text and "rs1801133\t1\t11856378\tAG" in text
    path = tmp_path / "wildtype-f5-called.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible()


def _seg_text(page):
    return page.locator("#drawer-segregation-container").inner_text().lower()


def test_demo_apoe_e4e4_drawer_says_every_child_inherits_e4(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    open_apoe(page)
    page.locator(".partner-sim-btn[data-partner='wildtype']").click()
    # An e4/e4 parent with a partner who has no e4 gives every child exactly one copy: the "one copy" row is 100% and the
    # "two copies" and "no copy" rows are 0% (the element ids keep their old names; the first row is "two copies").
    expect(page.locator("#sim-p-carrier")).to_have_text("100%")
    expect(page.locator("#sim-p-affected")).to_have_text("0%")
    expect(page.locator("#sim-p-wildtype")).to_have_text("0%")
    text = _seg_text(page)
    assert "inheriting the e4 allele" in text or "inheriting the c allele" in text, text
    for word in FORBIDDEN_FOR_NON_MENDELIAN:
        assert word not in text, f"'{word}' appears in the APOE e4/e4 drawer: {text}"


def test_wildtype_f5_drawer_has_no_affected_status_and_no_fifty_percent(loaded_page, tmp_path):
    page = loaded_page
    _analyse(page, _wildtype_f5_file(tmp_path))
    show_table(page)
    page.locator("[data-filter='negative']").click()
    page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs6025')")).click()
    wait_drawer_open(page)
    text = _seg_text(page)
    for word in FORBIDDEN_FOR_NON_MENDELIAN:
        assert word not in text, f"'{word}' appears in the wild-type F5 drawer: {text}"
    assert "50%" not in text, text
    page.locator(".partner-sim-btn[data-partner='wildtype']").click()
    # A wild-type patient with a partner who has no variant passes on nothing: only the "no copy" row is 100%.
    expect(page.locator("#sim-p-wildtype")).to_have_text("100%")
    expect(page.locator("#sim-p-carrier")).to_have_text("0%")
    expect(page.locator("#sim-p-affected")).to_have_text("0%")


def test_csv_has_no_half_risk_for_wildtype_loci(loaded_page, tmp_path):
    page = loaded_page
    _analyse(page, _wildtype_f5_file(tmp_path))
    with page.expect_download() as info:
        page.evaluate("() => window.__lucidase.exportCsvReport()")
    rows = list(csv.DictReader(Path(info.value.path()).read_text(encoding="utf-8").splitlines()))
    wildtype = {r["rsID"]: r for r in rows if r["rsID"] in ("rs6025", "rs1799945", "rs1800562", "rs1799963")}
    assert set(wildtype) == {"rs6025", "rs1799945", "rs1800562", "rs1799963"}
    for rsid, row in wildtype.items():
        for column, value in row.items():
            assert value not in ("0.5", "0.50", "0.25"), f"{rsid} {column} = {value} for a wild-type locus"
    # Genotype-aware columns: a wild-type patient transmits nothing, and only Mendelian genes have an affected figure.
    assert wildtype["rs6025"]["Child_Inherits_Allele_Wildtype_Partner"] == "0"
    assert wildtype["rs6025"]["Child_Affected_Unscreened_Partner"] == "N/A"  # F5 is a risk factor, not Mendelian
    assert wildtype["rs1800562"]["Child_Affected_Unscreened_Partner"] == "0"  # HFE recessive, wild-type patient
    by_rsid = {r["rsID"]: r for r in rows}
    assert by_rsid["rs1801133"]["Child_Inherits_Allele_Wildtype_Partner"] == "0.5"  # MTHFR het patient
    assert by_rsid["rs1801133"]["Child_Affected_Unscreened_Partner"] == "N/A"  # trait: no disease wording


def test_demo_hfe_double_het_is_phase_unknown(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    section = page.locator("#assortment-cards-container").inner_text().lower()
    assert "possible compound heterozygote" in section, section
    assert "phase unknown" in section, section
    assert "trans phase" not in section
    assert "synergistic" not in section


# Owner ruling 2026-10-04: a multi-locus finding may rest on an Unclear reading, but it must say so.
MULTI_LOCUS_CAUTION = "This pairing relies on a reading Lucidase marks as unclear, so treat it with extra caution."


def _assert_component(row, rsid, word, state):
    """One component of a multi-locus card: its marker, its own result word and the StateMark shape for its state."""
    item = row.locator(f'[data-component-rsid="{rsid}"]')
    expect(item).to_have_count(1)
    expect(item).to_contain_text(rsid)
    expect(item).to_contain_text(word)
    expect(item.locator(f".lds-mark.lds-mark-{state}")).to_have_count(1)


def test_demo_multi_locus_cards_show_each_component_word_and_caution_on_unclear(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    rows = page.locator("#assortment-cards-container > div")
    compound = rows.filter(has_text="Possible compound heterozygote")
    pairing = rows.filter(has_text="Co-occurring variant alleles")
    expect(compound).to_have_count(1)
    expect(pairing).to_have_count(1)

    # HFE: C282Y is Found, H63D's own word is Unclear, so the card carries the caution line.
    _assert_component(compound, "rs1800562", "Found", "supported_and_observed")
    _assert_component(compound, "rs1799945", "Unclear", "insufficient_evidence")
    caution = page.get_by_text(MULTI_LOCUS_CAUTION, exact=True)
    expect(compound.get_by_text(MULTI_LOCUS_CAUTION, exact=True)).to_have_count(1)  # positive control

    # F5 + F2: both Found, no caution line (same locator as the positive control above).
    _assert_component(pairing, "rs6025", "Found", "supported_and_observed")
    _assert_component(pairing, "rs1799963", "Found", "supported_and_observed")
    expect(pairing.get_by_text(MULTI_LOCUS_CAUTION, exact=True)).to_have_count(0)
    expect(caution).to_have_count(1)

    # The existing inspect buttons are kept.
    expect(compound.locator("button.btn-inspect-gene[data-gene='HFE']")).to_have_count(1)
    expect(pairing.locator("button.btn-inspect-gene")).to_have_count(2)


# --- The simulator's words (design RecordInspector): rows, notes and the "How this is worked out" sentence.
NEUTRAL_ROWS = ["Child gets two copies", "Child gets one copy", "Child gets no copy"]
# Complete penetrance: the two-copies chance is the affected chance. Partial or unstated: only a genotype chance.
MENDELIAN_ROWS = ["Child affected (two copies)", "Child is a carrier (one copy)", "Child gets no copy"]
PARTIAL_PENETRANCE_ROWS = ["Child gets two copies", "Child is a carrier (one copy)", "Child gets no copy"]
PARTNERS = ("unscreened", "carrier", "affected", "wildtype")


def _row_labels(page):
    return [
        page.locator(f"#sim-p-{row}").locator("xpath=preceding-sibling::span").inner_text()
        for row in ("affected", "carrier", "wildtype")
    ]


def _main_line(page):
    """The simulator's visible text except the "How this is worked out" sentence (which may name the model)."""
    return (
        page.locator("#drawer-segregation-container")
        .evaluate(
            """(el) => { const c = el.cloneNode(true);
              c.querySelectorAll('#drawer-sim-method, [hidden]').forEach((n) => n.remove());
              return c.innerText; }"""
        )
        .lower()
    )


def _open_record(page, finding_id):
    row = page.locator(f"#report-groups article.lds-finding[data-finding-id='{finding_id}']")
    row.locator("button.lds-finding-open").click()
    wait_drawer_open(page)
    expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", finding_id)


def _non_mendelian_ids(page):
    return page.evaluate(
        """() => window.__lucidase.state.records
          .filter((r) => r.segregation && !r.segregation.mendelian_disease && r.id !== window.__lucidase.state.apoe.id
                         && r.role !== 'apoe_component')
          .map((r) => r.id)"""
    )


def test_a_non_mendelian_locus_gets_copy_words_and_no_disease_words_for_every_partner(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    ids = _non_mendelian_ids(page)
    assert ids, "the demo has a non-Mendelian locus with a genotype"
    for finding_id in ids[:2]:
        _open_record(page, finding_id)
        for partner in PARTNERS:
            page.locator(f".partner-sim-btn[data-partner='{partner}']").click()
            assert _row_labels(page) == NEUTRAL_ROWS, (finding_id, partner)
            text = _seg_text(page)
            for word in FORBIDDEN_FOR_NON_MENDELIAN:
                assert word not in text, f"'{word}' for non-Mendelian {finding_id} ({partner}): {text}"
        scope = page.locator("#drawer-sim-scope")
        expect(scope).to_be_visible()
        expect(scope).to_have_text(
            re.compile(r"^These are chances of inheriting the .+ allele\. They say nothing about health\.$")
        )
        expect(page.locator("#drawer-sim-adjusted")).to_be_hidden()
        expect(page.locator("#drawer-seg-penetrance")).to_be_hidden()


def test_the_main_line_does_not_name_the_model_but_how_it_is_worked_out_does(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    hfe_id = page.evaluate("() => window.__lucidase.state.records.find((r) => r.gene === 'HFE').id")
    for finding_id in (_non_mendelian_ids(page)[0], hfe_id):
        _open_record(page, finding_id)
        main = _main_line(page)
        jargon_words = ("2pq", "hardy", "weinberg") + (("penetrance",) if finding_id != hfe_id else ())
        for jargon in jargon_words:
            assert jargon not in main, (finding_id, jargon, main)
        rows = " ".join(_row_labels(page)).lower()
        assert "penetrance" not in rows, rows
        expect(page.locator("#drawer-sim-method")).to_have_text(re.compile(r"^How this is worked out: .*Hardy-Weinberg"))


def test_hfe_shows_the_design_rows_and_a_penetrance_adjusted_figure_that_comes_from_the_kb(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    page.locator("button.btn-inspect-gene[data-gene='HFE']").first.click()
    wait_drawer_open(page)
    penetrance = page.evaluate("() => window.__lucidase.state.genes.HFE.inheritance.penetrance")
    assert 0 < penetrance < 1, "HFE's stated penetrance is below 1"
    assert _row_labels(page) == PARTIAL_PENETRANCE_ROWS
    adjusted = page.locator("#sim-effective-risk")
    label = adjusted.locator("xpath=preceding-sibling::span")
    expect(adjusted).to_be_visible()
    assert label.inner_text().startswith("Child affected, adjusted"), label.inner_text()
    expect(page.locator("#drawer-sim-scope")).to_be_hidden()
    expect(page.locator("#drawer-seg-penetrance")).to_be_visible()
    for partner, first in (("carrier", 25.0), ("affected", 50.0), ("wildtype", 0.0)):
        page.locator(f".partner-sim-btn[data-partner='{partner}']").click()
        expect(page.locator("#sim-p-affected")).to_have_text(f"{first:g}%")
        expect(adjusted).to_have_text(f"{round(first * penetrance * 10) / 10:g}%")
    # The sentence quotes the same stated penetrance.
    expect(page.locator("#drawer-sim-method")).to_contain_text(f"{penetrance * 100:g}%")


def _open_hfe_with_penetrance(page, value):
    def tamper(route):
        kb = json.loads(route.fetch().text())
        kb["genes"]["HFE"]["inheritance"]["penetrance"] = value
        route.fulfill(status=200, content_type="application/json", body=json.dumps(kb))

    page.route("**/knowledge-base.json", tamper)
    goto_ready(page, page.base_url)
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    page.locator("button.btn-inspect-gene[data-gene='HFE']").first.click()
    wait_drawer_open(page)


def test_the_adjusted_figure_follows_the_kb_penetrance(page):
    _open_hfe_with_penetrance(page, 0.4)
    page.locator(".partner-sim-btn[data-partner='affected']").click()
    expect(page.locator("#sim-p-affected")).to_have_text("50%")
    expect(page.locator("#sim-effective-risk")).to_have_text("20%")  # 50% x 0.4, a value no source file holds
    expect(page.locator("#drawer-sim-method")).to_contain_text("40%")


def test_the_adjusted_row_is_dropped_when_the_kb_penetrance_is_one(page):
    _open_hfe_with_penetrance(page, 1)
    assert _row_labels(page) == MENDELIAN_ROWS
    expect(page.locator("#drawer-sim-adjusted")).to_be_hidden()
    assert "penetrance" not in page.locator("#drawer-sim-method").inner_text().lower()


def test_moving_from_hfe_to_a_non_mendelian_locus_restores_the_neutral_view(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    hfe_id = page.evaluate("() => window.__lucidase.state.records.find((r) => r.gene === 'HFE').id")
    _open_record(page, hfe_id)
    expect(page.locator("#drawer-sim-adjusted")).to_be_visible()
    assert _row_labels(page) == PARTIAL_PENETRANCE_ROWS
    _open_record(page, _non_mendelian_ids(page)[0])
    expect(page.locator("#drawer-sim-adjusted")).to_be_hidden()
    expect(page.locator("#drawer-seg-penetrance")).to_be_hidden()
    expect(page.locator("#drawer-sim-scope")).to_be_visible()
    assert _row_labels(page) == NEUTRAL_ROWS


def test_a_locus_with_a_penetrance_of_one_has_no_adjusted_row_in_the_demo(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    cftr = page.evaluate(
        "() => { const r = window.__lucidase.state.records.find((x) => x.gene === 'CFTR' && x.segregation); return r ? r.id : null; }"
    )
    assert cftr, "the demo has a CFTR locus with a genotype"
    assert page.evaluate("() => window.__lucidase.state.genes.CFTR.inheritance.penetrance") == 1
    _open_record(page, cftr)
    assert _row_labels(page) == MENDELIAN_ROWS
    expect(page.locator("#drawer-sim-adjusted")).to_be_hidden()


def test_multi_locus_card_chips_are_neutral_not_category_tones(loaded_page):
    """"Across genes" cards say what they found in words; their chips carry no result-category colour."""
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    cards = page.locator("#assortment-cards-container")
    expect(cards.locator(".lds-tag-neutral")).to_have_count(4)  # positive control: two neutral chips on each card
    expect(cards.locator(".lds-tag[class*='lds-tag-cat-']")).to_have_count(0)
