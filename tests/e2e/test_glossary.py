"""The inline glossary (design system components/core/Term, ledger DS2-10).

A glossary word in copy Lucidase writes is a button with a dotted underline; its plain definition (src/glossary.js,
the one place the definitions live) opens on hover, on focus and on tap or click, Escape closes it and keeps focus on
the word, a press elsewhere closes it, and one is open at a time. Below 560px the definition sits at the foot of the
viewport inside the 16px gutters (controller addendum). Knowledge-base text, headings, buttons and table cells never
carry a Term.

The definitions are read from the page's own glossary module, never typed in here (web/tests/glossary.test.mjs pins
the strings).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from conftest import WAIT_TIMEOUT_MS, WEB_DIR, show_table, wait_drawer_open

NARROW = {"width": 390, "height": 844}
TERM = "button.lds-term"
OPEN = f"{TERM}[aria-expanded='true']"

# Every placement on the analysis page: (region, glossary word, the word as the page spells it). The first
# occurrence of a word in a section only, in copy Lucidase writes.
PLACEMENTS = [
    ("#section-hero", "variant", "variant"),  # What it can't do
    ("#section-hero", "marker", "Markers"),  # What it can't do
    ("#coverage-guardrail-banner", "chip", "chip"),  # the scope notice
    ("#summary-prose", "variant", "variant"),  # the Summary sentence (design system AnalysisScreen)
    ("#summary .lds-counts", "allele", "alleles"),  # the Carrier status count's help line
    ("#summary-legend [data-legend-state='insufficient_evidence']", "genotype", "genotype"),  # Unclear help line
    ("#group-risk .lds-section-aside", "variant", "Variants"),
    ("#group-risk .lds-section-aside", "risk factor", "risk factor"),
    ("#group-carrier .lds-section-aside", "variant", "Variants"),
    ("#assortment-section .lds-section-aside", "variant", "variants"),
]

GLOSSARY_JS = "async () => ({ ...(await import('./src/glossary.js')).GLOSSARY })"

# The places a Term must never be: knowledge-base text (statements, limitations, the technical line, the table, the
# Inspector), headings and buttons.
FORBIDDEN = (
    ".lds-finding-statement, .lds-finding-limit, .lds-finding-tech, #variants-tbody, #variant-drawer, "
    "#assortment-cards-container, h1, h2, h3, button:not(.lds-term)"
)


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    expect(page.locator(f"#summary-prose {TERM}")).to_have_count(1)


def _pop(page, term):
    return page.locator(f"#{term.get_attribute('aria-describedby')}")


def _expect_open(page, term):
    expect(term).to_have_attribute("aria-expanded", "true")
    expect(_pop(page, term)).to_be_visible()
    expect(page.locator(OPEN)).to_have_count(1)


def _expect_closed(page, term):
    expect(term).to_have_attribute("aria-expanded", "false")
    expect(_pop(page, term)).to_be_hidden()


def _narrow_touch_page(browser, base_url):
    context = browser.new_context(viewport=NARROW, has_touch=True, is_mobile=True)
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")), lambda r: r.abort())
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.wait_for_function("() => window.__lucidase !== undefined")
    return context, page


def test_each_placed_word_is_a_dotted_button_with_its_one_definition(loaded_page):
    page = loaded_page
    _load_demo(page)
    glossary = page.evaluate(GLOSSARY_JS)
    for region, word, shown in PLACEMENTS:
        term = page.locator(f"{region} {TERM}[data-term='{word}']")
        expect(term, f"{region} {word}").to_have_count(1)
        expect(term).to_have_text(shown)
        expect(term).to_have_attribute("type", "button")
        expect(term).to_have_attribute("aria-expanded", "false")
        assert term.evaluate("el => getComputedStyle(el).textDecorationStyle") == "dotted", (region, word)
        assert term.evaluate("el => el.parentElement.classList.contains('lds-termwrap')"), (region, word)
        pop = _pop(page, term)
        expect(pop).to_have_count(1)
        expect(pop).to_have_attribute("role", "tooltip")
        expect(pop).to_have_class("lds-term-pop")
        expect(pop).to_have_text(glossary[word])
        expect(pop).to_be_hidden()
        # The popover directly follows its word (styles.css opens it with the `+` combinator).
        assert term.evaluate("el => el.nextElementSibling.id") == term.get_attribute("aria-describedby")
    # These are all the Terms on the page: no word is wrapped twice in a section, and none anywhere else.
    expect(page.locator(TERM)).to_have_count(len(PLACEMENTS))
    ids = page.locator(TERM).evaluate_all("els => els.map((el) => el.getAttribute('aria-describedby'))")
    assert len(set(ids)) == len(ids)
    # The definitions are written once, in the glossary module, never in the HTML.
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for definition in glossary.values():
        assert definition not in html


def test_focus_opens_and_escape_closes_keeping_focus_on_the_word(loaded_page):
    page = loaded_page
    _load_demo(page)
    term = page.locator(f"#summary-prose {TERM}")
    term.focus()
    _expect_open(page, term)
    page.keyboard.press("Escape")
    _expect_closed(page, term)
    assert term.evaluate("el => document.activeElement === el")
    # Focus elsewhere and back opens it again, and blur closes it.
    page.locator("#results-h").focus()
    term.focus()
    _expect_open(page, term)
    page.locator("#results-h").focus()
    _expect_closed(page, term)


def test_hover_opens_reaches_the_definition_and_leaving_closes(loaded_page):
    page = loaded_page
    _load_demo(page)
    term = page.locator(f"#group-risk .lds-section-aside {TERM}[data-term='risk factor']")
    term.scroll_into_view_if_needed()
    term.hover()
    _expect_open(page, term)
    # The pointer can move down onto the definition to read it.
    _pop(page, term).hover()
    _expect_open(page, term)
    page.locator("#results-h").hover()
    _expect_closed(page, term)
    # Escape also closes a definition the pointer opened.
    term.hover()
    _expect_open(page, term)
    page.keyboard.press("Escape")
    _expect_closed(page, term)


def test_click_toggles_and_a_click_elsewhere_closes(loaded_page):
    page = loaded_page
    _load_demo(page)
    term = page.locator(f"#summary-prose {TERM}")
    term.hover()
    _expect_open(page, term)
    page.keyboard.press("Escape")
    _expect_closed(page, term)
    term.click()  # the pointer is already on the word, so this click alone opens it
    _expect_open(page, term)
    term.click()
    _expect_closed(page, term)
    term.click()
    _expect_open(page, term)
    page.mouse.move(5, 5)  # leaving with the mouse closes it; reopen with the keyboard to test a click elsewhere
    _expect_closed(page, term)
    page.locator("#results-h").focus()
    term.focus()
    _expect_open(page, term)
    page.locator("#summary-h").click()
    _expect_closed(page, term)
    # A press elsewhere closes it even where the press does not move focus (iOS Safari does not focus a tapped button).
    term.focus()
    _expect_open(page, term)
    page.locator("#summary-h").dispatch_event("pointerdown")
    _expect_closed(page, term)
    assert term.evaluate("el => document.activeElement === el")


def test_only_one_definition_is_open_at_a_time(loaded_page):
    page = loaded_page
    _load_demo(page)
    first = page.locator(f"#summary-prose {TERM}")
    second = page.locator(f"#group-risk .lds-section-aside {TERM}[data-term='variant']")
    first.focus()
    _expect_open(page, first)
    second.hover()
    _expect_open(page, second)
    _expect_closed(page, first)
    expect(page.locator(".lds-term-pop:visible")).to_have_count(1)


def test_no_term_in_knowledge_base_text_headings_buttons_or_table_cells(loaded_page):
    page = loaded_page
    _load_demo(page)
    show_table(page)
    page.locator("#report-groups button.lds-finding-open").first.click()
    wait_drawer_open(page)
    # Positive controls: the knowledge-base statements do say "variant", the table has rows, and the same selector
    # finds the Terms in the page's own copy.
    statements = page.locator(".lds-finding-statement").all_inner_texts()
    assert any("variant" in s.lower() for s in statements), statements
    assert page.locator("#variants-tbody tr").count() > 0
    assert page.locator(f".lds-section-aside {TERM}").count() > 0
    assert page.locator(f"#summary-prose {TERM}").count() == 1
    # And none of them is in a place a Term must never be.
    for selector in FORBIDDEN.split(", "):
        assert page.locator(f"{selector} .lds-term").count() == 0, selector


def test_at_390px_a_tap_opens_the_definition_inside_the_viewport_with_no_sideways_scroll(browser, base_url):
    context, page = _narrow_touch_page(browser, base_url)
    try:
        _load_demo(page)
        for region, word, _ in [p for p in PLACEMENTS if not p[0].startswith(("#section-hero", "#assortment"))]:
            term = page.locator(f"{region} {TERM}[data-term='{word}']")
            term.scroll_into_view_if_needed()
            term.tap()
            _expect_open(page, term)
            box = _pop(page, term).bounding_box()
            # Pinned to the foot of the viewport, inside the 16px gutters (controller addendum).
            assert abs(box["x"] - 16) <= 0.5 and abs(box["x"] + box["width"] - (NARROW["width"] - 16)) <= 0.5, (region, box)
            assert box["y"] >= 0 and abs(box["y"] + box["height"] - (NARROW["height"] - 16)) <= 0.5, (region, box)
            overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 0, f"{region}: the page scrolls sideways by {overflow}px"
            # A second tap closes it.
            term.tap()
            _expect_closed(page, term)
        # A tap elsewhere closes an open one.
        term = page.locator(f"#summary-prose {TERM}")
        term.scroll_into_view_if_needed()
        term.tap()
        _expect_open(page, term)
        page.locator("#summary-h").tap()
        _expect_closed(page, term)
    finally:
        context.close()


@pytest.mark.parametrize("width", [600, 1440])
def test_on_wider_screens_every_definition_stays_inside_the_viewport(browser, base_url, width):
    context = browser.new_context(viewport={"width": width, "height": 900})
    context.set_default_timeout(WAIT_TIMEOUT_MS)
    context.route(lambda url: not url.startswith(("http://127.0.0.1", "data:", "blob:")), lambda r: r.abort())
    page = context.new_page()
    try:
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_function("() => window.__lucidase !== undefined")
        _load_demo(page)
        terms = page.locator(TERM)
        checked = 0
        for i in range(terms.count()):
            term = terms.nth(i)
            if not term.is_visible():
                continue
            term.scroll_into_view_if_needed()
            term.focus()
            _expect_open(page, term)
            box = _pop(page, term).bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width - 16 + 0.5, (term.inner_text(), box)
            overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 0, f"{term.inner_text()}: the page scrolls sideways by {overflow}px"
            checked += 1
        assert checked >= 5, checked
    finally:
        context.close()
