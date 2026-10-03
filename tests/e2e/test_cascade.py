"""Cascade guard: daisyUI, then src/styles.css, then the Tailwind utilities, in <head>.

The old Play CDN appended its generated sheet after styles.css, so utilities beat the app's own rules of equal
specificity; the vendored sheet keeps that order. With the design system, styles.css also carries the daisyUI theme
bridge, which must come after daisyUI's own themes. If the sheets are reordered these assertions fail: a `hidden`
utility stops hiding a design-system component, and daisyUI's theme colours replace the design system's.
"""

from __future__ import annotations

from playwright.sync_api import expect

INK_DARK = "rgb(237, 242, 245)"  # --ink in the dark theme (#EDF2F5)
PAPER_DARK = "rgb(11, 17, 23)"  # --paper in the dark theme (#0B1117)
B1_DARK = "20.008% 0.0185 245.32"  # the bridge's daisyUI base-100 in the dark theme (#0F171E)


def _style(page, selector, *props):
    return page.evaluate(
        "([sel, props]) => { const s = getComputedStyle(document.querySelector(sel));"
        " return props.map(p => s[p]); }",
        [selector, list(props)],
    )


def test_stylesheets_load_daisyui_then_app_styles_then_utilities(loaded_page):
    hrefs = loaded_page.evaluate(
        "() => [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.getAttribute('href'))"
        ".filter(h => !h.includes('typekit'))"
    )
    assert hrefs == ["src/vendor/daisyui-4.12.10.min.css", "src/styles.css", "src/vendor/tailwind.css"], hrefs


def test_utilities_beat_design_system_components(loaded_page):
    # .lds-alert sets display:grid; the `hidden` utility on the same element must win.
    (display,) = _style(loaded_page, "#analysis-error", "display")
    assert display == "none", display
    # The design system's dropzone survives daisyUI and preflight: a dashed control border.
    (border,) = _style(loaded_page, "#dropzone", "borderTopStyle")
    assert border == "dashed", border
    # Preflight (in tailwind.css) resets links to `color: inherit`; the restated design-system rule must win.
    loaded_page.evaluate(
        "() => { const a = document.createElement('a'); a.id = 'cascade-probe'; a.href = '#'; a.textContent = 'x';"
        " document.querySelector('main').append(a); }"
    )
    (decoration,) = _style(loaded_page, "#cascade-probe", "textDecorationLine")
    assert decoration == "underline", decoration


def test_design_system_theme_beats_daisyui_theme_in_dark(loaded_page):
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    loaded_page.locator("#btn-theme-toggle").click()
    expect(loaded_page.locator("html")).to_have_attribute("data-theme", "dark")
    # Let the colour transition finish before reading the computed value.
    loaded_page.wait_for_function("() => document.body.getAnimations().length === 0")
    background, color = _style(loaded_page, "body", "backgroundColor", "color")
    assert background == PAPER_DARK and color == INK_DARK, (background, color)
    b1 = loaded_page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--b1').trim()")
    assert b1 == B1_DARK, f"daisyUI's own dark theme won over the design-system bridge: {b1}"
