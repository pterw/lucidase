"""The Summary as the results overview: prose, the karyogram and its legend (DS2-05).

Design system (ui_kits/web/AnalysisScreen.jsx "Summary", components/report/Karyogram.jsx, KaryogramLegend.jsx): a
serif sentence with the counts, the karyogram with the file's marker density and one mark per checked locus, and the
KaryogramLegend with a count per result word. Selecting a mark opens that result in the docked Inspector, the same
way a FindingRow's Details button does. The APOE record is read from two loci, so both of its marks open it.

Every expected value is computed from the page's own state, view model and KB, never typed in.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, REPO_ROOT, WAIT_TIMEOUT_MS, WEB_DIR, wait_drawer_closed, wait_drawer_open

NARROW = {"width": 390, "height": 844}
WILDTYPE = REPO_ROOT / "tests" / "e2e" / "fixtures" / "wildtype-23andme.txt"
KB = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))
RECORD_STATES = ("supported_and_observed", "supported_not_observed", "not_tested_by_array", "insufficient_evidence")
COUNT_IDS = {
    "supported_and_observed": "count-state-observed",
    "supported_not_observed": "count-state-negative",
    "not_tested_by_array": "count-state-gaps",
    "insufficient_evidence": "count-state-insufficient",
    "outside_coverage": "count-state-outside",
}
PROSE = "#summary-prose"
LEGEND = "#summary-legend"
MAP = "#summary-map"
MARKS = f"{MAP} .kary-locus"

# The demo with every per-locus state (the same edit as test_grouped_report.py ALL_STATES_TEXT): rs6025 dropped
# (Not on your chip), rs1800562 wild-type (Not found) and rs1799945 unreadable (Unclear).
ALL_STATES_TEXT = (
    re.sub(r"^rs6025[^\n]*\n", "", DEMO_FILE.read_text(encoding="utf-8"), flags=re.M)
    .replace("rs1800562\t6\t26093141\tAG", "rs1800562\t6\t26093141\tGG")
    .replace("rs1799945\t6\t26092913\tCG", "rs1799945\t6\t26092913\tTT")
)

# Every KB locus's state and the record it belongs to, from the page state. A listed single-locus record is its own
# locus; the APOE record's component loci belong to the APOE record. Topic and word from the KB genes and view model.
LOCI_JS = """async () => {
  const vm = await import('./src/view-model.js');
  const s = window.__lucidase.state;
  const out = {};
  for (const r of [...s.records, ...s.negativeChecks, ...s.arrayGaps, ...s.insufficientEvidence]) {
    if (!r.components) out[r.rsid] = { state: r.coverage_state, record: r.id, gene: r.gene };
  }
  if (s.apoe) for (const c of s.apoe.components) out[c.rsid] = { state: c.coverage_state, record: s.apoe.id, gene: s.apoe.gene };
  for (const v of Object.values(out)) {
    v.topic = s.genes[v.gene].topic;
    v.word = vm.RESULT_WORDS[v.state].label;
  }
  return out;
}"""

# The computed shape of a mark's core: everything that tells the states apart except colour (test_karyogram.py).
CORE_SHAPE = """(el) => {
  const s = getComputedStyle(el);
  return [s.fill !== s.stroke, s.clipPath, s.strokeDasharray].join('|');
}"""


def _analyse_text(page, tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    _analyse(page, path)


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator(MARKS).first).to_be_attached()


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator(MARKS).first).to_be_attached()


def _int(text):
    return int(text.replace(",", ""))


def _prose_counts(text):
    """The figures in the Summary sentence, by what they count. A clause that is absent maps to None."""

    def grab(pattern):
        m = re.search(pattern, text)
        return None if m is None else _int(m.group(1))

    return {
        "checks": grab(r"ran ([\d,]+) checks? on your file"),
        "supported_and_observed": grab(r"found in ([\d,]+)"),
        "supported_not_observed": grab(r"not found in ([\d,]+)"),
        "not_tested_by_array": grab(r"([\d,]+) (?:was|were) not on your chip"),
        "insufficient_evidence": grab(r"([\d,]+) (?:was|were) unclear"),
        "outside_coverage": grab(r"([\d,]+) other markers? in your file (?:was|were) counted but not interpreted"),
    }


def _report_counts(page):
    """FindingRows in the grouped report under each result, by the state class on the row's mark."""
    return {
        state: page.locator(f"#report-groups article.lds-finding > .lds-mark-{state}").count()
        for state in RECORD_STATES
    }


@pytest.mark.parametrize("sample", ["demo", "wildtype", "all-states"])
def test_prose_counts_equal_the_legend_and_the_grouped_report(loaded_page, tmp_path, sample):
    page = loaded_page
    if sample == "demo":
        _load_demo(page)
    elif sample == "wildtype":
        _analyse(page, WILDTYPE)
    else:
        _analyse_text(page, tmp_path, "all-states-23andme.txt", ALL_STATES_TEXT)
    prose = _prose_counts(page.locator(PROSE).inner_text())
    report = _report_counts(page)
    outside = page.evaluate("() => window.__lucidase.state.coverageSummary.outside_coverage_count")
    words = page.evaluate("async () => (await import('./src/view-model.js')).RESULT_WORDS")

    assert prose["checks"] == sum(report.values()) == page.locator("#report-groups article.lds-finding").count()
    assert prose["checks"] > 0
    assert prose["outside_coverage"] == outside
    for state, count_id in COUNT_IDS.items():
        item = page.locator(f'{LEGEND} li.lds-legend-item[data-legend-state="{state}"]')
        expect(item).to_have_count(1)
        expect(item.locator(".lds-statemark")).to_have_text(words[state]["label"])
        expect(item.locator(f".lds-statemark > .lds-mark-{state}")).to_have_count(1)
        expect(item.locator(".lds-legend-help")).to_have_text(words[state]["help"])
        count = item.locator(f'.lds-legend-count[data-legend-count="{state}"]')
        expect(count).to_have_attribute("id", count_id)
        legend = _int(count.inner_text())
        if state == "outside_coverage":
            assert legend == prose[state] == outside, (state, legend, prose)
        elif state == "not_tested_by_array" and report[state] == 0:
            # "Not on your chip" is said only when some check was not on the chip.
            assert prose[state] is None and legend == 0, (prose, legend)
        else:
            assert legend == prose[state] == report[state], (state, legend, prose, report)
    if sample != "demo":
        assert prose["not_tested_by_array"] == report["not_tested_by_array"] > 0  # positive control for the absence


def test_every_checked_locus_has_exactly_one_mark_in_its_state_shape(loaded_page, tmp_path):
    page = loaded_page
    _analyse_text(page, tmp_path, "all-states-23andme.txt", ALL_STATES_TEXT)
    loci = page.evaluate(LOCI_JS)
    assert set(loci) == set(KB["loci"]), "every KB locus has a state on the page"
    marks = page.locator(MARKS)
    expect(marks).to_have_count(len(KB["loci"]))
    shapes = {}
    for rsid, locus in loci.items():
        mark = page.locator(f'{MARKS}[data-rsid="{rsid}"]')
        expect(mark).to_have_count(1)
        expect(mark).to_have_class(re.compile(rf"(^|\s)kary-state-{locus['state']}(\s|$)"))
        expect(mark).to_have_attribute("data-state", locus["state"])
        shapes.setdefault(locus["state"], set()).add(mark.locator(".kary-core").evaluate(CORE_SHAPE))
    # Positive control: all four states are on this map, each in one shape, and no two states share a shape.
    assert set(shapes) == set(RECORD_STATES), shapes
    assert all(len(s) == 1 for s in shapes.values()), shapes
    assert len({next(iter(s)) for s in shapes.values()}) == len(RECORD_STATES), shapes
    # The density track is drawn from the file.
    assert page.locator(f"{MAP} .kary-bin:not(.kary-bin-empty)").count() > 0


def test_each_mark_is_a_keyboard_button_named_by_topic_and_word(loaded_page):
    page = loaded_page
    _load_demo(page)
    loci = page.evaluate(LOCI_JS)
    for rsid, locus in loci.items():
        mark = page.locator(f'{MARKS}[data-rsid="{rsid}"]')
        expect(mark).to_have_attribute("tabindex", "0")
        expect(mark).to_have_attribute("role", "button")
        name = mark.get_attribute("aria-label")
        assert locus["topic"] in name and locus["word"] in name and rsid in name, (rsid, name, locus)
    # The figure is not an image, which would hide its buttons from assistive technology.
    assert page.locator(f"{MAP} svg").get_attribute("role") != "img"


def _selected_ids(page):
    return page.locator("#report-groups article.lds-finding.is-selected").evaluate_all(
        "els => els.map((el) => el.dataset.findingId)"
    )


def _focused_rsid(page):
    return page.evaluate("() => document.activeElement && document.activeElement.getAttribute('data-rsid')")


def test_clicking_a_mark_opens_its_record_and_selects_its_row(loaded_page):
    page = loaded_page
    _load_demo(page)
    loci = page.evaluate(LOCI_JS)
    single = next(r for r, l in loci.items() if l["record"] == r and l["state"] == "supported_and_observed")
    apoe = sorted(r for r, l in loci.items() if l["record"] != r)
    assert len(apoe) == 2, loci  # positive control: the APOE record is read from two loci

    page.locator(f'{MARKS}[data-rsid="{single}"]').click()
    wait_drawer_open(page)
    expect(page.locator("#drawer-rsid")).to_have_text(single)
    expect(page.locator("#drawer-title")).to_have_text(loci[single]["topic"])
    assert _selected_ids(page) == [single]
    expect(page.locator(f'{MARKS}[data-rsid="{single}"]')).to_have_class(re.compile(r"(^|\s)is-selected(\s|$)"))

    # Each APOE locus opens the one APOE record, and swaps the open record.
    for rsid in apoe:
        page.locator(f'{MARKS}[data-rsid="{rsid}"]').click()
        expect(page.locator("#drawer-rsid")).to_have_attribute("data-record-id", loci[rsid]["record"])
        assert _selected_ids(page) == [loci[rsid]["record"]]
        for other in apoe:
            expect(page.locator(f'{MARKS}[data-rsid="{other}"]')).to_have_class(re.compile(r"(^|\s)is-selected(\s|$)"))
        expect(page.locator(f'{MARKS}[data-rsid="{single}"]')).not_to_have_class(re.compile(r"(^|\s)is-selected(\s|$)"))

    page.locator("#btn-close-drawer").click()
    wait_drawer_closed(page)
    assert _selected_ids(page) == []
    expect(page.locator(f"{MARKS}.is-selected")).to_have_count(0)


@pytest.mark.parametrize("key", ["Enter", " "])
def test_a_focused_mark_opens_with_the_keyboard_and_escape_returns_focus_to_it(loaded_page, key):
    page = loaded_page
    _load_demo(page)
    loci = page.evaluate(LOCI_JS)
    rsid = next(r for r, l in loci.items() if l["record"] == r and l["state"] == "supported_not_observed")
    mark = page.locator(f'{MARKS}[data-rsid="{rsid}"]')
    mark.focus()
    assert _focused_rsid(page) == rsid
    # Whether the page's own handling cancelled the key's default action (Space would scroll the page).
    page.evaluate("() => window.addEventListener('keydown', (e) => { window.__keyPrevented = e.defaultPrevented; })")
    page.keyboard.press(key)
    wait_drawer_open(page)
    expect(page.locator("#drawer-rsid")).to_have_text(rsid)
    assert _selected_ids(page) == [rsid]
    assert page.evaluate("() => document.getElementById('variant-drawer').contains(document.activeElement)")
    assert page.evaluate("() => window.__keyPrevented") is True, "the key opened the record, not scrolled the page"
    page.keyboard.press("Escape")
    wait_drawer_closed(page)
    assert _focused_rsid(page) == rsid

    # The close button also gives focus back to the mark.
    page.keyboard.press(key)
    wait_drawer_open(page)
    page.locator("#btn-close-drawer").click()
    wait_drawer_closed(page)
    assert _focused_rsid(page) == rsid


def test_no_sideways_scroll_on_a_phone_and_the_map_stays_in_its_box(browser, base_url):
    context = browser.new_context(viewport=NARROW)
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")), lambda r: r.abort())
    page = context.new_page()
    try:
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_function("() => window.__lucidase !== undefined")
        _load_demo(page)
        expect(page.locator(f"{MAP} svg")).to_be_visible()
        overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls sideways by {overflow}px"
        box = page.locator(MAP).bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= NARROW["width"], box
        for name in ("prose", "legend"):
            b = page.locator(f"#summary-{name}").bounding_box()
            assert b["x"] >= 0 and b["x"] + b["width"] <= NARROW["width"], (name, b)
    finally:
        context.close()


def test_on_a_phone_the_map_keeps_a_readable_size_and_scrolls_inside_its_own_box(browser, base_url):
    """At 390px the map keeps its drawn size (labels at least 10px, WCAG-minded tap targets) and scrolls sideways
    inside its own box, a named, keyboard-scrollable region, never the page."""
    context = browser.new_context(viewport=NARROW)
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")), lambda r: r.abort())
    page = context.new_page()
    try:
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_function("() => window.__lucidase !== undefined")
        _load_demo(page)
        box = page.locator(MAP)
        expect(box.locator("svg")).to_be_visible()
        expect(box).to_have_attribute("role", "region")
        expect(box).to_have_attribute("aria-label", "Chromosome map")
        expect(box).to_have_attribute("tabindex", "0")

        overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls sideways by {overflow}px"
        assert box.evaluate("el => getComputedStyle(el).overflowX") == "auto"
        dims = box.evaluate("el => ({ scroll: el.scrollWidth, client: el.clientWidth })")
        assert dims["scroll"] > dims["client"], dims

        # Rendered sizes: the SVG's scale times each label's font size, and each mark's halo as drawn.
        scale = box.locator("svg").evaluate("svg => svg.getBoundingClientRect().width / svg.viewBox.baseVal.width")
        sizes = box.locator(".kary-label").evaluate_all("els => els.map((t) => parseFloat(getComputedStyle(t).fontSize))")
        assert sizes and min(sizes) * scale >= 10, (sizes, scale)
        halos = box.locator(".kary-locus .kary-halo").evaluate_all(
            "els => els.map((c) => c.getBoundingClientRect().width)"
        )
        assert halos and min(halos) >= 20, halos

        # The region scrolls from the keyboard.
        box.focus()
        page.keyboard.press("ArrowRight")
        page.wait_for_function("() => document.getElementById('summary-map').scrollLeft > 0")
        overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls sideways by {overflow}px"
    finally:
        context.close()


def test_the_density_notice_shows_only_when_the_file_does_not_say_its_genome_version(loaded_page, tmp_path):
    page = loaded_page
    notice = page.locator("#summary-density-notice")
    _load_demo(page)
    expect(notice).to_be_hidden()
    assert page.locator(f"{MAP} .kary-bin:not(.kary-bin-empty)").count() > 0
    text = (REPO_ROOT / "tests" / "e2e" / "fixtures" / "apoe-e3e4-23andme.txt").read_text(encoding="utf-8")
    no_build = "\n".join(line for line in text.splitlines() if "build" not in line.lower()) + "\n"
    assert "build" not in no_build.lower()
    page.locator("#btn-use-another-file").click()
    _analyse_text(page, tmp_path, "no-build.txt", no_build)
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("doesn't say which genome version")
    assert page.locator(f"{MAP} .kary-bin:not(.kary-bin-empty)").count() == 0
    expect(page.locator(MARKS)).to_have_count(len(KB["loci"]))


def test_a_map_that_cannot_be_laid_out_takes_the_one_error_path(loaded_page):
    """The results wait for the map; the worker's karyogram action failing is the analysis failing, never a half page."""
    page = loaded_page
    real = (WEB_DIR / "src" / "worker.js").read_text(encoding="utf-8")
    call = "await buildKaryogram(text, fileName);"
    assert real.count(call) == 1  # the edit below applies
    broken = real.replace(call, "throw new Error('map layout failed');")
    page.route(
        "**/src/worker.js",
        lambda route: route.fulfill(status=200, content_type="application/javascript", body=broken),
    )
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible(timeout=WAIT_TIMEOUT_MS)
    expect(page.locator("#analysis-error-detail")).to_have_text("map layout failed")
    expect(page.locator("#results-section")).to_be_hidden()
    expect(page.locator("#progress-section")).to_be_hidden()
    expect(page.locator("#btn-load-demo")).to_be_enabled()
    assert page.evaluate("() => window.__lucidase.state.pendingAnalysis") is None
    # Positive control: the same page, with the real worker, shows the results and the map.
    page.unroute("**/src/worker.js")
    _load_demo(page)
    expect(page.locator("#analysis-error")).to_be_hidden()
