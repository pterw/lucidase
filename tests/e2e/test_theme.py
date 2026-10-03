"""The theme follows the device until the person overrides it from the footer (the design system's ThemeToggle).

Only an override is stored ("lucidase-theme"); "Use device setting" clears it and appears only after an override.
src/theme-boot.js applies the stored override before the app module runs, so a dark override never flashes light.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from conftest import goto_ready

STORED = "() => localStorage.getItem('lucidase-theme')"


def test_page_follows_a_dark_device_with_nothing_stored(page):
    page.emulate_media(color_scheme="dark")
    goto_ready(page, page.base_url)
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle-text")).to_have_text("Light theme")
    expect(page.locator("#btn-theme-system")).to_be_hidden()
    assert page.evaluate(STORED) is None


def test_an_override_is_stored_and_use_device_setting_clears_it(page):
    page.emulate_media(color_scheme="dark")
    goto_ready(page, page.base_url)
    page.locator("#btn-theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    assert page.evaluate(STORED) == "light"
    expect(page.locator("#btn-theme-system")).to_be_visible()

    goto_ready(page, page.base_url)  # the stored override beats the dark device
    expect(page.locator("html")).to_have_attribute("data-theme", "light")

    page.locator("#btn-theme-system").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    assert page.evaluate(STORED) is None
    expect(page.locator("#btn-theme-system")).to_be_hidden()


def test_a_device_change_is_followed_live_without_an_override(page):
    goto_ready(page, page.base_url)
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


@pytest.mark.allow_console_errors
def test_the_stored_theme_applies_before_the_app_module_runs(page):
    # With app.js refused, only theme-boot.js can have set the attribute.
    page.add_init_script("localStorage.setItem('lucidase-theme', 'dark')")
    page.route("**/src/app.js", lambda route: route.abort())
    page.goto(page.base_url, wait_until="load")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    assert page.evaluate("() => window.__lucidase") is None


def test_a_legacy_light_value_does_not_pin_a_dark_device(page):
    # Before the design system every first visit stored "light" without a choice, so an unversioned "light" is not
    # an override. An unversioned "dark" was always a choice, and is kept.
    page.emulate_media(color_scheme="dark")
    page.goto(page.base_url + "/karyogram.html")  # same origin: seed storage as the old page left it
    page.evaluate("() => { localStorage.clear(); localStorage.setItem('lucidase-theme', 'light'); }")
    goto_ready(page, page.base_url)
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    assert page.evaluate(STORED) is None
    expect(page.locator("#btn-theme-system")).to_be_hidden()

    page.evaluate("() => { localStorage.clear(); localStorage.setItem('lucidase-theme', 'dark'); }")
    page.emulate_media(color_scheme="light")
    goto_ready(page, page.base_url)
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    assert page.evaluate(STORED) == "dark"

    # After the migration, a light override chosen now is kept.
    page.emulate_media(color_scheme="dark")
    page.locator("#btn-theme-toggle").click()
    goto_ready(page, page.base_url)
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
