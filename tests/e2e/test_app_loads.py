"""Sanity E2E: the page loads against a real uvicorn process.

If this passes, the rest of the E2E suite has a solid foundation:
- subprocess lifecycle works
- ADHD_DATA_DIR isolation works
- Playwright + Chromium are correctly installed
- the page's bootstrap script executes
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_clock_renders_with_hhmm_format(page, live_server):
    page.goto(live_server.url)
    # Clock starts as "--:--" in HTML; tickClock() updates it on boot.
    # expect() polls up to 5s for the regex to match.
    expect(page.locator("#clock")).to_have_text(re.compile(r"^\d{2}:\d{2}$"))


@pytest.mark.e2e
def test_default_tab_is_tasks_on_fresh_load(page, live_server):
    page.goto(live_server.url)
    # Fresh browser context = empty localStorage = the default tab logic kicks
    # in and selects Tasks (the recent fix).
    expect(page.locator(".tab.active")).to_have_attribute("data-tab", "tasks")


@pytest.mark.e2e
def test_day_heading_reads_today(page, live_server):
    page.goto(live_server.url)
    expect(page.locator("#day-heading")).to_have_text("Today")


@pytest.mark.e2e
def test_isolated_data_dir_starts_empty(page, live_server):
    page.goto(live_server.url)
    # The Tasks tab is empty initially (per-test data dir).
    expect(page.locator("#tasks-empty")).to_be_visible()
    # Inbox count badge shows 0.
    expect(page.locator("#inbox-count")).to_have_text("0")
    expect(page.locator("#tasks-count")).to_have_text("0")
