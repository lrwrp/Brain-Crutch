"""End-to-end: ← / → date arrows (Tier 1 #4 / Phase 7).

The arrows step the visible day by ±1 calendar day. They feed through the
same setDate path as the picker, so DAY_CHANGED fires and renderers refresh.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_next_arrow_advances_one_day(page, live_server):
    page.goto(live_server.url)

    # Seed the picker to a known mid-month date so we don't worry about
    # month/year rollovers in the basic case.
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )
    expect(page.locator("#date-picker")).to_have_value("2099-06-15")

    page.locator("#date-next").click()
    expect(page.locator("#date-picker")).to_have_value("2099-06-16")


@pytest.mark.e2e
def test_prev_arrow_decrements_one_day(page, live_server):
    page.goto(live_server.url)
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )

    page.locator("#date-prev").click()
    expect(page.locator("#date-picker")).to_have_value("2099-06-14")


@pytest.mark.e2e
def test_next_arrow_crosses_month_boundary(page, live_server):
    """End-of-month → first-of-next-month. UTC arithmetic in the handler
    should sidestep DST drift; verify the simpler month-boundary case here."""
    page.goto(live_server.url)
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-30'; el.dispatchEvent(new Event('change')); }"
    )

    page.locator("#date-next").click()
    expect(page.locator("#date-picker")).to_have_value("2099-07-01")


@pytest.mark.e2e
def test_prev_arrow_crosses_year_boundary(page, live_server):
    page.goto(live_server.url)
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-01-01'; el.dispatchEvent(new Event('change')); }"
    )

    page.locator("#date-prev").click()
    expect(page.locator("#date-picker")).to_have_value("2098-12-31")


@pytest.mark.e2e
def test_arrows_update_day_heading(page, live_server):
    """The heading reads Today / Yesterday / Tomorrow / formatted date.
    Pressing → from Today should land on Tomorrow."""
    page.goto(live_server.url)
    expect(page.locator("#day-heading")).to_have_text("Today")

    page.locator("#date-next").click()
    expect(page.locator("#day-heading")).to_have_text("Tomorrow")

    page.locator("#date-prev").click()
    expect(page.locator("#day-heading")).to_have_text("Today")

    page.locator("#date-prev").click()
    expect(page.locator("#day-heading")).to_have_text("Yesterday")
