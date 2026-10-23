"""The grouped report, its FindingRows and the table one click away (DS2-03, DS2-04, DS2-08).

After the Summary, the results read as the design system's four groups (Pharmacology, Health risk factors, Carrier
status, Traits), one FindingRow per interpreted check: a shape mark, the topic, the plain statement, the gene, the
limitation (always visible) and the technical line. "Details" opens the drawer for that record. The technical table
is collapsed behind "Show the table". Expected values are computed from the page's own view model and the KB, never
typed in.
"""

from __future__ import annotations

import re

from playwright.sync_api import expect

from conftest import DEMO_FILE, show_table, wait_drawer_closed, wait_drawer_open

NARROW = {"width": 390, "height": 844}

# The demo with every per-locus state: rs6025 dropped (Not on your chip), rs1800562 wild-type (Not found) and
# rs1799945 unreadable (Unclear). The same edit as web/tests/view-model.test.mjs ALL_STATES_FILE.
ALL_STATES_TEXT = (
    re.sub(r"^rs6025[^\n]*\n", "", DEMO_FILE.read_text(encoding="utf-8"), flags=re.M)
    .replace("rs1800562\t6\t26093141\tAG", "rs1800562\t6\t26093141\tGG")
    .replace("rs1799945\t6\t26092913\tCG", "rs1799945\t6\t26092913\tTT")
)

# What the page's view model says each check should look like, from window.__lucidase.state and view-model.js.
EXPECTED_JS = """async () => {
  const vm = await import('./src/view-model.js');
  const s = window.__lucidase.state;
  const seen = new Set();
  const checks = [...s.records, ...s.negativeChecks, ...s.arrayGaps, ...s.insufficientEvidence]
    .filter((r) => !seen.has(r.id) && seen.add(r.id));
  return {
    groups: vm.REPORT_GROUPS.map((g) => ({ id: g.id, title: g.title, aside: g.aside })),
    checks: checks.map((r) => ({
      id: r.id,
      gene: r.gene,
      group: vm.groupIdForModel(s.genes[r.gene].inheritance.model),
      topic: s.genes[r.gene].topic,
      state: r.coverage_state,
      word: vm.RESULT_WORDS[r.coverage_state].label,
      limitation: r.limitation,
      technical: (r.components || [r]).map((l) => l.rsid + ' · ' + (l.genotype_display || 'No reading')).join(' + '),
      markers: (r.components || [r]).map((l) => l.rsid).join(' and '),
    })),
  };
}"""


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()


def _load_all_states(page, tmp_path):
    path = tmp_path / "all-states-23andme.txt"
    path.write_text(ALL_STATES_TEXT, encoding="utf-8")
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible()


def _group_sections(page):
    return page.locator("#report-groups > section.lds-section")


def _row(page, finding_id):
    return page.locator(f'#report-groups article.lds-finding[data-finding-id="{finding_id}"]')


def test_the_four_groups_follow_the_summary_in_the_design_system_order(loaded_page):
    page = loaded_page
    _load_demo(page)
    expected = page.evaluate(EXPECTED_JS)
    sections = _group_sections(page)
    expect(sections).to_have_count(len(expected["groups"]))
    for i, group in enumerate(expected["groups"]):
        section = sections.nth(i)
        expect(section).to_be_visible()
        expect(section).to_have_attribute("id", f"group-{group['id']}")
        heading = section.locator(".lds-section-head h2.lds-section-title")
        expect(heading).to_have_text(group["title"])
        expect(section).to_have_attribute("aria-labelledby", heading.get_attribute("id"))
        # The rendered text: a glossary word's closed definition (test_glossary.py) is not part of what is read.
        expect(section.locator(".lds-section-aside")).to_have_text(group["aside"], use_inner_text=True)
    # After the Summary, before "Across genes" and the table.
    order = page.evaluate(
        """() => ['summary-h', 'report-groups', 'assortment-section', 'table-h']
              .map((id) => document.getElementById(id))
              .every((el, i, all) => i === 0 || (all[i - 1].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING))"""
    )
    assert order is True


def test_every_check_is_one_row_in_its_gene_group(loaded_page, tmp_path):
    page = loaded_page
    _load_all_states(page, tmp_path)
    expected = page.evaluate(EXPECTED_JS)
    assert {c["state"] for c in expected["checks"]} == {
        "supported_and_observed", "supported_not_observed", "not_tested_by_array", "insufficient_evidence",
    }
    rows = page.locator("#report-groups article.lds-finding")
    expect(rows).to_have_count(len(expected["checks"]))
    shown = rows.evaluate_all(
        "els => els.map((el) => ({ id: el.dataset.findingId, group: el.closest('section').id }))"
    )
    assert sorted(r["id"] for r in shown) == sorted(c["id"] for c in expected["checks"])
    by_id = {c["id"]: c for c in expected["checks"]}
    for row in shown:
        assert row["group"] == f"group-{by_id[row['id']]['group']}", row
    # APOE is one composite row; its two loci are never rows of their own.
    assert sum(1 for r in shown if by_id[r["id"]]["gene"] == "APOE") == 1
    for rsid in ("rs429358", "rs7412"):
        expect(_row(page, rsid)).to_have_count(0)


def test_each_row_shows_its_topic_word_mark_limitation_and_technical_line(loaded_page, tmp_path):
    page = loaded_page
    _load_all_states(page, tmp_path)
    expected = page.evaluate(EXPECTED_JS)
    for check in expected["checks"]:
        row = _row(page, check["id"])
        expect(row).to_have_count(1)
        topic = row.locator("h3.lds-finding-topic")
        expect(topic).to_have_text(check["topic"])
        expect(row).to_have_attribute("aria-labelledby", topic.get_attribute("id"))
        expect(row.locator(".lds-finding-gene")).to_have_text(check["gene"])
        # The mark's shape class matches the state, and it carries the plain word: colour is never the only signal.
        mark = row.locator(":scope > span.lds-mark")
        expect(mark).to_have_count(1)
        assert set(mark.get_attribute("class").split()) == {"lds-mark", "lds-mark-16", f"lds-mark-{check['state']}"}
        expect(mark).to_have_attribute("role", "img")
        expect(mark).to_have_attribute("aria-label", check["word"])
        expect(row.locator(".lds-finding-statement")).to_be_visible()
        expect(row.locator(".lds-finding-tech")).to_have_text(check["technical"])
        limit = row.locator(".lds-finding-limit")
        if check["limitation"]:
            expect(limit).to_be_visible()
            expect(limit).to_contain_text("What this can’t tell you:")
            expect(limit).to_contain_text(check["limitation"])
            expect(limit.locator(".lds-icon.lds-i-info")).to_have_count(1)
        else:
            expect(limit).to_have_count(0)
        button = row.locator("button.lds-finding-open")
        expect(button).to_have_text("Details")
        # Topic plus markers: two loci can share a topic (HFE), and each button needs its own accessible name.
        expect(button).to_have_attribute("aria-label", f"Details for {check['topic']}, {check['markers']}")
        expect(button).to_have_attribute("aria-expanded", "false")
        expect(button.locator(".lds-icon.lds-i-chevron-right")).to_have_count(1)


def test_details_opens_the_drawer_and_escape_returns_focus_to_it(loaded_page):
    page = loaded_page
    _load_demo(page)
    for finding_id in ("rs4244285", page.evaluate("() => window.__lucidase.state.apoe.id")):
        row = _row(page, finding_id)
        button = row.locator("button.lds-finding-open")
        button.focus()
        page.keyboard.press("Enter")
        wait_drawer_open(page)
        # The open record's id (the APOE subtitle shows its markers, not the id; test_inspector.py).
        expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", finding_id)
        assert page.locator("#variant-drawer").evaluate("el => el.contains(document.activeElement)")
        expect(button).to_have_attribute("aria-expanded", "true")
        expect(row).to_have_class(re.compile(r"(^|\s)is-selected(\s|$)"))
        expect(page.locator("#report-groups .lds-finding.is-selected")).to_have_count(1)

        page.keyboard.press("Escape")
        wait_drawer_closed(page)
        expect(button).to_be_focused()
        expect(button).to_have_attribute("aria-expanded", "false")
        expect(page.locator("#report-groups .lds-finding.is-selected")).to_have_count(0)

    # Opening a record from the table selects its row too: one selection, wherever it was opened from.
    show_table(page)
    page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs4244285')")).click()
    wait_drawer_open(page)
    expect(_row(page, "rs4244285").locator("button.lds-finding-open")).to_have_attribute("aria-expanded", "true")
    page.locator("#btn-close-drawer").click()
    wait_drawer_closed(page)
    expect(page.locator("#report-groups .lds-finding.is-selected")).to_have_count(0)


def test_the_table_is_one_click_away_and_then_searchable(loaded_page):
    page = loaded_page
    _load_demo(page)
    section = page.locator("#results-table")
    expect(section.locator("#table-h")).to_have_text("All results as a table")
    expect(section.locator(".lds-section-aside")).to_have_text(
        "The same results with the technical columns, for checking against other tools."
    )
    button = section.locator("#btn-show-table")
    expect(button).to_be_visible()
    expect(button).to_have_text("Show the table")
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(button).to_have_attribute("aria-controls", "table-panel")
    assert {"lds-btn", "lds-btn-secondary", "lds-btn-sm"} <= set(button.get_attribute("class").split())
    expect(button.locator(".lds-icon.lds-i-table")).to_have_count(1)
    for hidden in ("#table-panel", "#variants-tbody", "#search-input", "[data-filter='every']"):
        expect(page.locator(hidden)).to_have_count(1)  # present in the page, so "hidden" is not an absent selector
        expect(page.locator(hidden)).to_be_hidden()

    button.click()
    expect(page.locator("#table-panel")).to_be_visible()
    expect(button).to_have_attribute("aria-expanded", "true")
    expect(page.locator("#search-input")).to_be_focused()
    search = page.locator("#search-input")
    expect(search).to_have_attribute("type", "search")
    search.fill("rs4244285")
    rows = page.locator("#variants-tbody tr")
    expect(rows).to_have_count(1)
    expect(rows.first.locator("td").first).to_have_text("rs4244285")
    expect(page.locator("#showing-count")).to_contain_text("Showing 1 of")


def test_the_open_table_fits_the_page_at_1440_and_390(loaded_page):
    page = loaded_page
    for size in ({"width": 1440, "height": 900}, NARROW):
        page.set_viewport_size(size)
        if not page.locator("#results-section").is_visible():
            _load_demo(page)
        show_table(page)
        overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls sideways by {overflow}px at {size['width']}px"
        # The table may scroll inside its own box, but the box ends inside the viewport.
        right = page.locator("#table-panel").evaluate("el => el.getBoundingClientRect().right")
        assert right <= size["width"] + 0.5, f"the table ends at {right}px at {size['width']}px"
