"""Cascade guard: Tailwind utilities must follow src/styles.css in <head>.

The old Play CDN appended its generated sheet after styles.css, so utilities beat
the app's own rules of equal specificity. If the vendored sheet is linked before
styles.css these assertions fail (dashed dropzone becomes solid, accent borders
vanish, .font-serif overrides text-*, dark utilities lose to .glass-panel).
"""

from __future__ import annotations

from playwright.sync_api import expect

SLATE_300 = "rgb(203, 213, 225)"


def _style(page, selector, *props):
    return page.evaluate(
        "([sel, props]) => { const s = getComputedStyle(document.querySelector(sel));"
        " return props.map(p => s[p]); }",
        [selector, list(props)],
    )


def test_utilities_beat_app_styles_in_light_mode(loaded_page):
    style, width = _style(loaded_page, "#dropzone", "borderTopStyle", "borderTopWidth")
    assert style == "dashed" and width == "2px", (style, width)
    (tagline,) = _style(loaded_page, "[data-design-id='brand.tagline']", "fontSize")
    assert tagline == "13px", tagline  # text-[13px] must beat .font-serif font-size
    (tracking,) = _style(loaded_page, "h1", "letterSpacing")
    assert tracking != "normal"


def test_accent_border_survives_after_results(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible(timeout=10000)
    card = "#apoe-status-card"
    expect(loaded_page.locator(card)).to_be_visible(timeout=10000)
    width, color = _style(loaded_page, card, "borderLeftWidth", "borderLeftColor")
    assert width == "4px", width
    assert color != SLATE_300, f"accent border colour lost: {color}"


def test_dark_utilities_beat_glass_panel(loaded_page):
    loaded_page.locator("#btn-theme-toggle").click()
    # Let the 200 ms colour transition finish before reading the computed value.
    loaded_page.wait_for_timeout(600)
    (background,) = _style(loaded_page, "#dropzone", "backgroundColor")
    # dark:bg-slate-900/40 -> alpha 0.4; .glass-panel would give 0.75
    assert background.endswith("0.4)"), background
