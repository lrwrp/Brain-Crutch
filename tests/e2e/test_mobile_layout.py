"""End-to-end: mobile top-level view switcher (Timeline / Triage).

On a phone-width viewport the two-column layout collapses to a single column
and a top-level switcher (``.app-views``) decides which of the two panels is
visible. On desktop the switcher is hidden and both panels show side by side.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 800}


@pytest.mark.e2e
def test_switcher_hidden_on_desktop_both_panels_show(page, live_server):
    page.set_viewport_size(DESKTOP)
    page.goto(live_server.url)

    expect(page.locator(".app-views")).to_be_hidden()
    expect(page.locator(".timeline-panel")).to_be_visible()
    expect(page.locator(".side")).to_be_visible()


@pytest.mark.e2e
def test_phone_defaults_to_timeline_view(page, live_server):
    page.set_viewport_size(PHONE)
    page.goto(live_server.url)

    expect(page.locator(".app-views")).to_be_visible()
    # Default view is Timeline: timeline panel shown, triage side hidden.
    expect(page.locator(".timeline-panel")).to_be_visible()
    expect(page.locator(".side")).to_be_hidden()
    expect(page.locator('.app-view[data-view="timeline"]')).to_have_class(
        "app-view active"
    )


@pytest.mark.e2e
def test_phone_tapping_triage_flips_visible_panel(page, live_server):
    page.set_viewport_size(PHONE)
    page.goto(live_server.url)

    page.locator('.app-view[data-view="triage"]').click()

    expect(page.locator(".side")).to_be_visible()
    expect(page.locator(".timeline-panel")).to_be_hidden()
    expect(page.locator("body")).to_have_attribute("data-mobile-view", "triage")

    # And back to Timeline.
    page.locator('.app-view[data-view="timeline"]').click()
    expect(page.locator(".timeline-panel")).to_be_visible()
    expect(page.locator(".side")).to_be_hidden()


@pytest.mark.e2e
def test_phone_view_choice_persists_across_reload(page, live_server):
    page.set_viewport_size(PHONE)
    page.goto(live_server.url)

    page.locator('.app-view[data-view="triage"]').click()
    expect(page.locator("body")).to_have_attribute("data-mobile-view", "triage")

    page.reload()
    # localStorage restores the Triage view on the next load.
    expect(page.locator("body")).to_have_attribute("data-mobile-view", "triage")
    expect(page.locator(".side")).to_be_visible()
    expect(page.locator(".timeline-panel")).to_be_hidden()
