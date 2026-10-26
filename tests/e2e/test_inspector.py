"""The docked, non-modal Inspector and the APOE Ligature (DS2-06, DS2-09).

Design system (components/navigation/Inspector.jsx, ui_kits/web/AnalysisScreen.jsx, RecordInspector.jsx): the
details pane is docked beside the results, sticky, var(--inspector-w) wide; below the layout's breakpoint it sits
under the list. It is non-modal: no backdrop, no focus trap, the list stays clickable, and choosing another row
swaps the record. Opening focuses the pane; Escape or the close button closes it and gives focus back to the opener.
The APOE composite (two markers read as one result) shows the Ligature figure in "What was found".

Expected values come from the page's own state and the KB, never typed in.
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import expect

from conftest import WAIT_TIMEOUT_MS, show_table, wait_drawer_closed, wait_drawer_open

NARROW = {"width": 390, "height": 844}
FIXTURES = Path(__file__).parent / "fixtures"
APOE_ONLY_RS429358 = FIXTURES / "apoe-only-rs429358-23andme.txt"  # rs7412 absent: no APOE diplotype
INSPECTOR = "#variant-drawer"
LIST = "#results-section .lds-results-main"
LIGATURE = f"{INSPECTOR} figure.lds-ligature"
CANT_TELL = "What this can’t tell you"


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    expect(page.locator("#report-groups article.lds-finding").first).to_be_visible()


def _row(page, finding_id):
    return page.locator(f"#report-groups article.lds-finding[data-finding-id='{finding_id}']")


def _details(page, finding_id):
    return _row(page, finding_id).locator("button.lds-finding-open")


def _apoe_id(page):
    return page.evaluate("() => window.__lucidase.state.apoe.id")


def _box(page, selector):
    return page.locator(selector).evaluate(
        "el => { const r = el.getBoundingClientRect(); return {left: r.left, right: r.right, top: r.top,"
        " bottom: r.bottom, width: r.width, height: r.height}; }"
    )


def _focused_is(page, selector):
    return page.locator(selector).evaluate("el => el === document.activeElement")


def _record(page, finding_id):
    """The open record's display facts, from the page state and the KB genes (never typed in)."""
    return page.evaluate(
        """(id) => {
          const s = window.__lucidase.state;
          const r = [...s.records, ...s.negativeChecks, ...s.arrayGaps, ...s.insufficientEvidence]
            .find((x) => x.id === id);
          return { id: r.id, gene: r.gene, topic: s.genes[r.gene].topic, word: r.stateLabel,
                   limitation: r.limitation, caveats: r.caveats, positionText: r.positionText, chromosomes: r.chromosomes,
                   mendelian: Boolean(r.segregation && r.segregation.mendelian_disease),
                   drug: r.drug_response, acmg: Boolean(r.acmg_actionable) };
        }""",
        finding_id,
    )


def _expect_notices(page, rec):
    """The notice block shows exactly when the record has a drug response or an ACMG SF gene."""
    notices = page.locator("#drawer-notices")
    if rec["drug"] is not None or rec["acmg"]:
        expect(notices).to_be_visible()
    else:
        expect(notices).to_be_hidden()


def _visible_section_titles(page):
    return page.locator(f"{INSPECTOR} .lds-isec-title").evaluate_all(
        "els => els.filter((el) => el.getClientRects().length > 0).map((el) => el.textContent.trim())"
    )


def test_docked_beside_the_list_non_modal_and_rows_swap_the_record(loaded_page):
    page = loaded_page
    _load_demo(page)
    first, second = "rs4244285", _apoe_id(page)

    _details(page, first).click()
    wait_drawer_open(page)
    expect(page.locator("#drawer-rsid")).to_have_text(first)

    # Beside the list, var(--inspector-w) wide, in the viewport: not over the page, not off-screen.
    side, main = _box(page, INSPECTOR), _box(page, LIST)
    inspector_w = page.evaluate(
        "() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--inspector-w'))"
    )
    assert side["left"] >= main["right"] + 16, (side, main)
    assert abs(side["width"] - inspector_w) <= 1, (side["width"], inspector_w)
    assert 0 <= side["top"] < page.viewport_size["height"]
    assert side["right"] <= page.viewport_size["width"]

    # Non-modal: no aria-modal, no dialog role, nothing inert, and the list is what is under the pointer.
    aside = page.locator(INSPECTOR)
    assert aside.get_attribute("aria-modal") is None
    assert aside.get_attribute("role") is None
    assert page.locator("[inert]").count() == 0
    other = _details(page, second)
    other.scroll_into_view_if_needed()
    assert other.evaluate(
        "el => { const r = el.getBoundingClientRect();"
        " return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) === el; }"
    ), "something covers the results list while the Inspector is open"

    # Choosing another row swaps the record and the selection, with no close in between.
    other.click()
    expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", second)
    wait_drawer_open(page)
    expect(page.locator("#report-groups .lds-finding.is-selected")).to_have_count(1)
    expect(_row(page, second)).to_have_class(re.compile(r"(^|\s)is-selected(\s|$)"))
    expect(_details(page, second)).to_have_attribute("aria-expanded", "true")
    expect(_details(page, first)).to_have_attribute("aria-expanded", "false")

    # Sticky: scrolling the page keeps the docked Inspector in view.
    page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight / 2)")
    page.wait_for_function(
        "() => { const r = document.getElementById('variant-drawer').getBoundingClientRect();"
        " return r.top >= 0 && r.top <= 32 && r.bottom <= window.innerHeight; }",
        timeout=WAIT_TIMEOUT_MS,
    )


def test_below_the_list_on_a_narrow_screen_scrolled_into_view_without_sideways_scroll(browser, base_url):
    context = browser.new_context(viewport=NARROW)
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")), lambda r: r.abort())
    page = context.new_page()
    try:
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_function("() => window.__lucidase !== undefined")
        _load_demo(page)
        _details(page, "rs4244285").click()
        wait_drawer_open(page)
        side, main = _box(page, INSPECTOR), _box(page, LIST)
        assert side["top"] >= main["bottom"], (side, main)
        assert abs(side["left"] - main["left"]) <= 1 and abs(side["width"] - main["width"]) <= 1, (side, main)
        # Opened below the list, it is brought into view.
        page.wait_for_function(
            "() => { const r = document.getElementById('variant-drawer').getBoundingClientRect();"
            " return r.top >= -1 && r.top < window.innerHeight / 2; }",
            timeout=WAIT_TIMEOUT_MS,
        )
        # Static there: the page scrolls, not the pane.
        assert page.locator(f"{INSPECTOR} .lds-inspector-body").evaluate(
            "el => el.scrollHeight <= el.clientHeight + 1"
        )
        overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls sideways by {overflow}px"
    finally:
        context.close()


def test_opening_focuses_the_inspector_and_escape_or_close_returns_focus_to_the_opener(loaded_page):
    page = loaded_page
    _load_demo(page)
    rec = _record(page, "rs4244285")

    # From a FindingRow's Details button, by keyboard.
    button = _details(page, "rs4244285")
    button.focus()
    page.keyboard.press("Enter")
    wait_drawer_open(page)
    assert _focused_is(page, INSPECTOR), "opening must focus the Inspector itself"
    expect(page.locator(INSPECTOR)).to_have_attribute("tabindex", "-1")
    expect(page.get_by_role("complementary", name=rec["topic"])).to_have_count(1)
    # No focus trap: Tab leaves the Inspector for the rest of the page.
    for _ in range(80):
        page.keyboard.press("Tab")
        if not page.locator(INSPECTOR).evaluate("el => el.contains(document.activeElement)"):
            break
    else:
        raise AssertionError("Tab never left the Inspector")
    page.locator(INSPECTOR).focus()
    page.keyboard.press("Escape")
    wait_drawer_closed(page)
    expect(button).to_be_focused()

    # From a table row, closed with the close button.
    show_table(page)
    tr = page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs4244285')"))
    tr.click()
    wait_drawer_open(page)
    assert _focused_is(page, INSPECTOR)
    page.locator("#btn-close-drawer").click()
    wait_drawer_closed(page)
    assert _focused_is(page, "#variants-tbody tr:has(td:first-child:text-is('rs4244285'))")

    # Escape closes it from anywhere on the page (the design system listens on the document), but a person who
    # moved on keeps their focus: it returns to the opener only from inside the Inspector.
    button.click()
    wait_drawer_open(page)
    page.locator("#search-input").focus()
    page.keyboard.press("Escape")
    wait_drawer_closed(page)
    expect(page.locator("#search-input")).to_be_focused()


def test_header_sections_and_footer_follow_the_record_inspector(loaded_page):
    page = loaded_page
    _load_demo(page)
    hfe = page.evaluate("() => window.__lucidase.state.records.find((r) => r.gene === 'HFE').id")
    seen_limitation = seen_mendelian = seen_transmission = False
    for finding_id in ("rs4244285", hfe):
        rec = _record(page, finding_id)
        _details(page, finding_id).click()
        wait_drawer_open(page)
        expect(page.locator("#drawer-rsid")).to_have_text(finding_id)

        # Header: the KB topic, then gene · marker · position, then the StateMark with its word.
        expect(page.locator("#drawer-title")).to_have_text(rec["topic"])
        expect(page.locator(f"{INSPECTOR} .lds-inspector-sub")).to_have_text(
            f"{rec['gene']} · {rec['id']} · chromosome {rec['chromosomes']}"
        )
        # The exact position moved to Technical details; it is not lost.
        expect(page.locator("#drawer-coord")).to_have_text(rec["positionText"])
        mark = page.locator(f"{INSPECTOR} .lds-inspector-meta .lds-statemark")
        expect(mark).to_have_text(rec["word"])
        expect(mark.locator(".lds-mark")).to_have_count(1)

        # Sections in the design system's order; the limitation section is there exactly when the record has one.
        expected = ["What was found"]
        if rec["limitation"] is not None:
            expected.append(CANT_TELL)
            seen_limitation = True
        if rec["caveats"]:
            expected.append("Caveats and scope")
        expected.append("If you have children" if rec["mendelian"] else "Passing it on")
        seen_mendelian |= rec["mendelian"]
        seen_transmission |= not rec["mendelian"]
        expected += [
            "Technical details",
            "Gene and protein context",
            "Human Protein Atlas expression",
            "Where the protein sits in the cell",
        ]
        assert _visible_section_titles(page) == expected

        # Notices (drug, ACMG) sit at the top of the body, before the first section.
        _expect_notices(page, rec)
        for box_id, present in (("#drawer-drug-box", rec["drug"] is not None), ("#drawer-acmg-box", rec["acmg"])):
            if present:
                expect(page.locator(box_id)).to_be_visible()
                assert page.locator(box_id).evaluate(
                    "el => Boolean(el.compareDocumentPosition(document.querySelector('#variant-drawer .lds-isec'))"
                    " & Node.DOCUMENT_POSITION_FOLLOWING)"
                )

        # The other-parent control uses the design system's option words.
        words = page.locator("#drawer-partner-buttons .partner-sim-btn").all_inner_texts()
        assert words == (
            ["Unscreened", "Carrier", "Affected", "No variant"]
            if rec["mendelian"]
            else ["Unscreened", "One copy", "Two copies", "No variant"]
        ), words
        expect(page.locator("#drawer-partner-buttons")).to_have_attribute("aria-label", "Other parent")

        # Footer: the evidence tier, then the ClinVar link (Button variant link, arrow-up-right).
        foot = page.locator(f"{INSPECTOR} .lds-inspector-foot")
        assert foot.locator("#drawer-footer-tier").evaluate(
            "el => Boolean(el.compareDocumentPosition(document.getElementById('drawer-clinvar-link'))"
            " & Node.DOCUMENT_POSITION_FOLLOWING)"
        )
        link = page.locator("#drawer-clinvar-link")
        expect(link).to_have_text("ClinVar record")
        expect(link.locator(".lds-icon.lds-i-arrow-up-right")).to_have_count(1)
        expect(link).to_have_attribute("target", "_blank")
        expect(link).to_have_attribute("rel", "noopener noreferrer")
        page.locator("#btn-close-drawer").click()
        wait_drawer_closed(page)
    # The demo covers both simulator headings and a limitation, so each branch above was exercised.
    assert seen_limitation and seen_mendelian and seen_transmission


def test_the_ligature_shows_the_apoe_record_and_only_the_apoe_record(loaded_page):
    page = loaded_page
    _load_demo(page)
    apoe = page.evaluate(
        "() => { const a = window.__lucidase.state.apoe;"
        " return { id: a.id, parts: a.components.map((c) => [c.rsid, c.genotype_display]),"
        " diplotype: a.diplotypeDisplay }; }"
    )
    assert [rsid for rsid, _ in apoe["parts"]] == ["rs429358", "rs7412"]
    assert all(gt for _, gt in apoe["parts"]) and apoe["diplotype"]

    # Positive control: the APOE composite shows one Ligature, in "What was found", with the record's values.
    _details(page, apoe["id"]).click()
    wait_drawer_open(page)
    figure = page.locator(LIGATURE)
    expect(figure).to_have_count(1)
    found = page.locator(f"{INSPECTOR} section.lds-isec", has=page.locator("h3", has_text="What was found"))
    expect(found.locator("figure.lds-ligature")).to_have_count(1)
    expect(figure.locator(".lds-ligature-markers > span")).to_have_text([f"{rsid} {gt}" for rsid, gt in apoe["parts"]])
    expect(figure.locator(".lds-ligature-result")).to_have_text(f"APOE {apoe['diplotype']}")
    expect(figure.locator("figcaption.lds-ligature-caption")).to_have_text("One result built from two markers")
    # APOE carries no drug response and no ACMG SF gene, so the empty notice block is hidden (rs4244285 below shows it).
    apoe_rec = _record(page, apoe["id"])
    assert apoe_rec["drug"] is None and not apoe_rec["acmg"]
    _expect_notices(page, apoe_rec)
    # The DS geometry, themed by classes only.
    svg = figure.locator("svg")
    expect(svg).to_have_attribute("viewBox", "0 0 240 34")
    expect(svg).to_have_attribute("aria-hidden", "true")
    expect(svg.locator("path.lds-ligature-arch")).to_have_attribute("d", "M30 32 C 30 4, 210 4, 210 32")
    circle = svg.locator("circle.lds-ligature-dot")
    assert [circle.get_attribute(a) for a in ("cx", "cy", "r")] == ["120", "11", "4"]
    assert page.locator(f"{LIGATURE} [fill], {LIGATURE} [stroke]").count() == 0

    # A single-marker record (same selector) has none, and swapping back to it removes the figure.
    for finding_id in ("rs4244285", page.evaluate("() => window.__lucidase.state.records.find((r) => r.gene === 'HFE').id")):
        _details(page, finding_id).click()
        expect(page.locator("#drawer-rsid")).to_have_text(finding_id)
        expect(page.locator(LIGATURE)).to_have_count(0)
        _expect_notices(page, _record(page, finding_id))
    assert _record(page, "rs4244285")["drug"] is not None


def test_the_ligature_says_not_available_for_a_missing_genotype_and_diplotype(loaded_page):
    page = loaded_page
    page.set_input_files("#file-input", str(APOE_ONLY_RS429358))
    expect(page.locator("#results-section")).to_be_visible()
    apoe = page.evaluate(
        "() => { const a = window.__lucidase.state.apoe;"
        " return { id: a.id, parts: a.components.map((c) => [c.rsid, c.genotype_display]),"
        " diplotype: a.diplotypeDisplay }; }"
    )
    # The fixture: rs429358 read, rs7412 absent, so there is no diplotype.
    assert apoe["parts"][0][1] and apoe["parts"][1][1] is None and apoe["diplotype"] is None
    _details(page, apoe["id"]).click()
    wait_drawer_open(page)
    figure = page.locator(LIGATURE)
    expect(figure.locator(".lds-ligature-markers > span")).to_have_text(
        [f"rs429358 {apoe['parts'][0][1]}", "rs7412 Not available"]
    )
    expect(figure.locator(".lds-ligature-result")).to_have_text("Not available")


# The simulator's words (polish pass): the design system calls the other person "Other parent", and the transmission
# subtitle speaks to the reader about their own file. Keyed by whether the gene is a Mendelian disease gene; the demo's
# Mendelian genes (HFE, CFTR) are autosomal recessive, so their figures are genotype probabilities.
SEG_WORDS = {
    False: {
        "sub": "The chance a child inherits the variant, from your genotype.",
        "unscreened": "Child inherits, if the other parent is unscreened",
        "second": "Child inherits, if the other parent has no variant",
    },
    True: {
        "sub": "The chance for each child, from your result and the other parent's status you pick.",
        "unscreened": "Risk if the other parent is unscreened (genotype probability)",
        "second": "Risk if the other parent is a carrier (genotype probability)",
    },
}


def test_the_simulator_names_the_other_parent_and_speaks_to_the_reader(loaded_page):
    page = loaded_page
    _load_demo(page)
    hfe = page.evaluate("() => window.__lucidase.state.records.find((r) => r.gene === 'HFE').id")
    seen = set()
    for finding_id in ("rs4244285", hfe):
        rec = _record(page, finding_id)
        seen.add(rec["mendelian"])
        _details(page, finding_id).click()
        wait_drawer_open(page)
        expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", finding_id)
        words = SEG_WORDS[rec["mendelian"]]
        expect(page.locator("#drawer-segregation-container [data-role='seg-title'] + p")).to_have_text(words["sub"])
        dt = "xpath=preceding-sibling::dt"
        expect(page.locator("#drawer-seg-risk-unscreened").locator(dt)).to_have_text(words["unscreened"])
        expect(page.locator("#drawer-seg-risk-carrier").locator(dt)).to_have_text(words["second"])
        expect(page.locator("#drawer-partner-model-note")).to_have_text(re.compile(r"^Other parent: unscreened\. "))
        # Nowhere in the Inspector a "partner" or a "patient"; the same text does name the other parent.
        text = page.locator(INSPECTOR).inner_text().lower()
        assert "other parent" in text
        for word in ("partner", "patient"):
            assert word not in text, (finding_id, word)
    assert seen == {True, False}, "the demo covers both simulator wordings"


def test_the_apoe_subtitle_names_the_gene_once_then_its_markers_and_chromosome(loaded_page):
    page = loaded_page
    _load_demo(page)
    apoe = page.evaluate(
        "() => { const a = window.__lucidase.state.apoe;"
        " return { id: a.id, gene: a.gene, rsids: a.components.map((c) => c.rsid), positionText: a.positionText, chromosomes: a.chromosomes }; }"
    )
    assert apoe["rsids"] == ["rs429358", "rs7412"] and apoe["positionText"]
    sub = page.locator(f"{INSPECTOR} .lds-inspector-sub")
    _details(page, apoe["id"]).click()
    wait_drawer_open(page)
    expect(sub).to_have_text(f"{apoe['gene']} · {' + '.join(apoe['rsids'])} · chromosome {apoe['chromosomes']}")
    expect(page.locator("#drawer-coord")).to_have_text(apoe["positionText"])
    assert sub.inner_text().count(apoe["gene"]) == 1
    expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", apoe["id"])
    # A single-marker record (same selectors): its marker is its id.
    _details(page, "rs4244285").click()
    expect(page.locator("#drawer-rsid")).to_have_text("rs4244285")
    expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", "rs4244285")


# DataList (design system components/report/DataList.jsx): a value is mono unless it is prose (mono: false), which is
# in the sans font. Prose here: the APOE figures' KB wording and the ClinVar review; data: genotype, frequency, magnitude.
PROSE_VALUES = ("#drawer-apoe-risk-ratio", "#drawer-apoe-lifetime", "#drawer-stars")
DATA_VALUES = ("#drawer-genotype", "#drawer-af", "#drawer-magnitude")


def test_datalist_prose_values_are_sans_and_data_values_mono(loaded_page):
    page = loaded_page
    _load_demo(page)
    _details(page, _apoe_id(page)).click()
    wait_drawer_open(page)

    def family(sel):
        return page.locator(sel).evaluate("el => getComputedStyle(el).fontFamily")

    sans = family(f"{INSPECTOR} .lds-datalist dt >> nth=0")
    assert "akzidenz-grotesk-next-pro" in sans, sans
    for sel in PROSE_VALUES:
        expect(page.locator(sel)).to_be_visible()
        assert family(sel) == sans, (sel, family(sel))
    for sel in DATA_VALUES:
        assert "input-mono" in family(sel), (sel, family(sel))
