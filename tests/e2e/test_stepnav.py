"""StepNav, the "Save a copy" step and the narrow "Pages" disclosure (DS2-07, DS2-12, DS2-11).

The steps follow the page: choosing or reading a file (or a failed read) is step 1, the results are step 2, the save
section is step 3. A done step is a button that goes back to it; step 1 from the results returns to the file chooser,
and step 3 cannot be reached before there are results. Below 560px of its own width the nav is the current step,
"Step N of 3" and a back link. Below 680px the header's page links sit behind a "Pages" disclosure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from conftest import WAIT_TIMEOUT_MS, WEB_DIR, goto_ready

NARROW = {"width": 390, "height": 844}
STEPS = ["Choose your file", "Read your results", "Save a copy"]
GUARDRAIL = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))["manifest"]["guardrail"]


def _states(page):
    return page.locator(".lds-stepnav .lds-step").evaluate_all("els => els.map(el => el.dataset.state)")


def _step(page, index):
    return page.locator(".lds-stepnav .lds-step").nth(index)


def _step_button(page, index):
    return _step(page, index).locator("button.lds-step-item")


def _load_demo(page):
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    expect(page.locator("#report-groups article.lds-finding").first).to_be_visible()


def _no_horizontal_scroll(page):
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0, f"the page scrolls sideways by {overflow}px"


def _fits_viewport(page, selectors):
    """Each region (and everything in it) ends inside the viewport.

    Names the region that overflows, which the page-wide check alone does not.
    """
    for selector in selectors:
        right = page.locator(selector).evaluate(
            "el => Math.max(el.getBoundingClientRect().right,"
            " ...[...el.querySelectorAll('*')].map(c => c.getBoundingClientRect().right))"
        )
        width = page.evaluate("() => document.documentElement.clientWidth")
        assert right <= width + 0.5, f"{selector} ends at {right}px, past the {width}px viewport"


def _assert_step_one(page):
    assert _states(page) == ["current", "upcoming", "upcoming"]
    current = page.locator(".lds-stepnav-list [aria-current='step']")
    expect(current).to_have_count(1)
    expect(current).to_contain_text(STEPS[0])
    # Nothing ahead of step 1 can be visited before there are results.
    expect(page.locator(".lds-stepnav-list button")).to_have_count(0)
    expect(page.locator("#section-hero")).to_be_visible()


def test_idle_page_is_step_one_and_no_later_step_can_be_visited(loaded_page):
    page = loaded_page
    nav = page.locator("nav.lds-stepnav")
    expect(nav).to_have_attribute("aria-label", "Steps")
    assert [t.strip() for t in nav.locator(".lds-step-item > span:last-child").all_inner_texts()] == STEPS
    _assert_step_one(page)
    expect(page.locator("#results-section")).to_be_hidden()


def test_a_failed_read_stays_on_step_one(page):
    page.add_init_script("window.Worker = function () { throw new Error('worker blocked'); };")
    goto_ready(page, page.base_url)
    page.locator("#btn-load-demo").click()
    expect(page.locator("#analysis-error")).to_be_visible()
    _assert_step_one(page)


def test_results_are_step_two_and_the_intro_gives_way_to_the_heading_actions(loaded_page):
    page = loaded_page
    _load_demo(page)
    assert _states(page) == ["done", "current", "upcoming"]
    current = page.locator(".lds-stepnav-list [aria-current='step']")
    expect(current).to_have_count(1)
    expect(current).to_contain_text(STEPS[1])
    # The done step shows the vendored check icon, never a unicode tick, and says "(done)" to a screen reader.
    done = _step_button(page, 0)
    expect(done).to_be_visible()
    expect(done.locator(".lds-step-dot .lds-icon.lds-i-check")).to_have_count(1)
    expect(done.locator(".sr-only")).to_contain_text("(done)")
    assert "✓" not in page.locator("nav.lds-stepnav").inner_text()
    # Step 3 is reachable once there are results.
    expect(_step_button(page, 2)).to_be_visible()

    expect(page.locator("#section-hero")).to_be_hidden()
    heading = page.locator("#results-h")
    assert heading.evaluate("el => el.tagName") == "H1"
    save = page.locator("#btn-goto-save")
    expect(save).to_have_text("Save a copy")
    expect(save.locator(".lds-i-download")).to_have_count(1)
    assert "lds-btn-secondary" in save.get_attribute("class") and "lds-btn-sm" in save.get_attribute("class")
    other = page.locator("#btn-use-another-file")
    expect(other).to_have_text("Use another file")
    assert "lds-btn-ghost" in other.get_attribute("class") and "lds-btn-sm" in other.get_attribute("class")


@pytest.mark.parametrize("trigger", ["step", "heading-button", "keyboard"])
def test_save_step_brings_the_save_section_into_view_and_focuses_it(loaded_page, trigger):
    page = loaded_page
    _load_demo(page)
    if trigger == "step":
        _step_button(page, 2).click()
    elif trigger == "heading-button":
        page.locator("#btn-goto-save").click()
    else:
        _step_button(page, 2).focus()
        page.keyboard.press("Enter")
    assert _states(page) == ["done", "done", "current"]
    expect(page.locator(".lds-stepnav-list [aria-current='step']")).to_contain_text(STEPS[2])
    expect(page.locator("#save-h")).to_be_focused()
    expect(page.locator("#save-h")).to_be_in_viewport()

    # Step 2 goes back to the top of the results.
    _step_button(page, 1).click()
    assert _states(page) == ["done", "current", "upcoming"]
    expect(page.locator("#results-h")).to_be_focused()


def test_save_section_holds_the_only_export_buttons_and_both_download(loaded_page):
    page = loaded_page
    _load_demo(page)
    section = page.locator("section#save")
    expect(section).to_be_visible()
    expect(section.locator("#save-h")).to_have_text("Save a copy")
    expect(section.locator(".lds-section-aside")).to_have_text("Files are made on this device. Nothing is sent anywhere.")
    # The old toolbar menu is gone: one button per id, both inside the save section.
    expect(page.locator(".dropdown")).to_have_count(0)
    for item_id, label, variant, icon, suffix in (
        ("btn-export-md", "Save the report (.md)", "lds-btn-primary", "lds-i-file-text", ".md"),
        ("btn-export-csv", "Save the table (.csv)", "lds-btn-secondary", "lds-i-table", ".csv"),
    ):
        expect(page.locator(f"#{item_id}")).to_have_count(1)
        button = section.locator(f"#{item_id}")
        assert button.evaluate("el => el.tagName") == "BUTTON"
        expect(button).to_have_text(label)
        assert variant in button.get_attribute("class")
        expect(button.locator(f".{icon}")).to_have_count(1)
        with page.expect_download(timeout=WAIT_TIMEOUT_MS) as info:
            button.click()
        assert info.value.suggested_filename.endswith(suffix)
        text = Path(info.value.path()).read_text(encoding="utf-8")
        if suffix == ".md":
            assert GUARDRAIL in text
        else:
            # The table carries no scope notice, so the page must not claim that it does.
            assert GUARDRAIL not in text
    # Using the save section is step 3.
    assert _states(page) == ["done", "done", "current"]
    words = section.inner_text()
    assert "Both copies include every result, its limitation and the scope notice" not in words, words
    assert "the table does not" in words, words


@pytest.mark.parametrize("trigger", ["step", "use-another-file"])
def test_step_one_returns_to_the_file_chooser_and_a_second_run_works(loaded_page, trigger):
    page = loaded_page
    _load_demo(page)
    if trigger == "step":
        _step_button(page, 0).click()
    else:
        page.locator("#btn-use-another-file").click()
    _assert_step_one(page)
    expect(page.locator("#results-section")).to_be_hidden()
    expect(page.locator("#progress-section")).to_be_hidden()
    expect(page.locator("#btn-browse-files")).to_be_focused()
    # The previous file's results are not kept: nothing is left to export.
    assert page.evaluate("() => window.__lucidase.state.qc") is None
    assert page.evaluate("() => window.__lucidase.state.records.length") == 0

    _load_demo(page)
    assert _states(page) == ["done", "current", "upcoming"]
    assert page.evaluate("() => window.__lucidase.state.records.length") > 0
    with page.expect_download(timeout=WAIT_TIMEOUT_MS) as info:
        page.locator("#btn-export-csv").click()
    assert info.value.suggested_filename.endswith(".csv")


def test_narrow_stepnav_shows_the_current_step_and_a_back_link(page):
    page.set_viewport_size(NARROW)
    goto_ready(page, page.base_url)
    nav = page.locator("nav.lds-stepnav")
    expect(nav.locator(".lds-stepnav-list")).to_be_hidden()
    compact = nav.locator(".lds-stepnav-compact")
    expect(compact).to_be_visible()
    expect(compact.locator(".lds-stepnav-current")).to_have_text(STEPS[0])
    expect(compact.locator(".lds-stepnav-current")).to_have_attribute("aria-current", "step")
    expect(compact.locator(".lds-stepnav-count")).to_have_text("Step 1 of 3")
    expect(compact.locator(".lds-stepnav-back")).to_be_hidden()
    _no_horizontal_scroll(page)

    _load_demo(page)
    expect(compact.locator(".lds-stepnav-current")).to_have_text(STEPS[1])
    expect(compact.locator(".lds-stepnav-count")).to_have_text("Step 2 of 3")
    back = compact.locator(".lds-stepnav-back")
    expect(back).to_be_visible()
    expect(back).to_have_text(STEPS[0])
    expect(back.locator(".lds-icon.lds-i-arrow-left")).to_have_count(1)
    assert "←" not in back.inner_text()
    _fits_viewport(page, ["header.lds-header", "nav.lds-stepnav", "#results-h", "#btn-use-another-file", "section#save"])
    _no_horizontal_scroll(page)  # the whole results page, long tags included (#qc-inferred-sex, #apoe-risk-ratio)

    page.locator("#btn-goto-save").click()
    expect(compact.locator(".lds-stepnav-count")).to_have_text("Step 3 of 3")
    expect(back).to_have_text(STEPS[1])
    back.click()
    expect(compact.locator(".lds-stepnav-count")).to_have_text("Step 2 of 3")
    back.click()
    expect(compact.locator(".lds-stepnav-count")).to_have_text("Step 1 of 3")
    expect(page.locator("#section-hero")).to_be_visible()
    _no_horizontal_scroll(page)


@pytest.mark.parametrize("path", ["index.html", "karyogram.html"])
def test_pages_disclosure_at_narrow_width(page, path):
    page.set_viewport_size(NARROW)
    page.goto(f"{page.base_url}/{path}", wait_until="networkidle")
    header = page.locator("header.lds-header")
    expect(header.locator(".lds-header-inner > nav.lds-nav")).to_be_hidden()
    toggle = header.locator("button.lds-pages-toggle")
    panel = page.locator("#lds-pages")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_text("Pages")
    expect(toggle).to_have_attribute("aria-controls", "lds-pages")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle.locator(".lds-i-menu")).to_have_count(1)
    expect(panel).to_be_hidden()
    _no_horizontal_scroll(page)

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle.locator(".lds-i-x")).to_have_count(1)
    expect(panel).to_be_visible()
    expect(panel).to_have_attribute("aria-label", "Main")
    assert [t.strip() for t in panel.locator("a.lds-navlink").all_inner_texts()] == ["Analysis", "Karyogram"]
    expect(panel.locator("a[aria-current='page']")).to_have_count(1)
    _no_horizontal_scroll(page)

    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(panel).to_be_hidden()
    expect(toggle).to_be_focused()

    toggle.click()
    expect(panel).to_be_visible()
    page.locator("main").click(position={"x": 5, "y": 5})
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(panel).to_be_hidden()

    # Only one "Main" nav is ever exposed at a time.
    page.set_viewport_size({"width": 1440, "height": 900})
    expect(toggle).to_be_hidden()
    expect(header.locator(".lds-header-inner > nav.lds-nav")).to_be_visible()


def test_the_stepnav_is_on_the_analysis_page_only(page):
    # Positive control first: the same selector must find the StepNav where it exists, or the absence check below
    # would pass vacuously after a rename.
    goto_ready(page, page.base_url)
    expect(page.locator("nav.lds-stepnav")).to_have_count(1)
    page.goto(f"{page.base_url}/karyogram.html", wait_until="networkidle")
    expect(page.locator("nav.lds-stepnav")).to_have_count(0)
