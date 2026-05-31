"""End-to-end: off-hours visual pressure (Tier 2 #19).

The 08:00-20:00 focus window is no longer a scheduling restriction
(see Tier 2 #18). It survives as a *visual* concept: the timeline
backdrop dims outside the window, and blocks placed outside get a
``data-off-hours="true"`` attribute that triggers dashed-edge styling
and a 🌙 corner glyph.

Tests use a stable far-future date so wall-clock has no influence.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


FUTURE = "2099-06-15"


def _schedule(page, *, title: str, start_min: int, duration_min: int) -> None:
    page.evaluate(
        """async (body) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            return r.ok;
        }""",
        {
            "title": title,
            "schedule": {
                "date": FUTURE,
                "startMin": start_min,
                "durationMin": duration_min,
            },
        },
    )


def _goto_future(page, live_server) -> None:
    page.goto(live_server.url)
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")


# --- per-block flag -----------------------------------------------------


@pytest.mark.e2e
def test_block_starting_before_8am_is_off_hours(page, live_server):
    _goto_future(page, live_server)
    # 07:00–07:30 — starts before DAY_START_MIN.
    _schedule(page, title="early start", start_min=420, duration_min=30)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="early start")
    expect(block).to_have_attribute("data-off-hours", "true")


@pytest.mark.e2e
def test_block_ending_after_8pm_is_off_hours(page, live_server):
    _goto_future(page, live_server)
    # 19:30–20:30 — ends after DAY_END_MIN.
    _schedule(page, title="late finish", start_min=1170, duration_min=60)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="late finish")
    expect(block).to_have_attribute("data-off-hours", "true")


@pytest.mark.e2e
def test_block_inside_focus_window_is_not_off_hours(page, live_server):
    _goto_future(page, live_server)
    # 12:00–13:00 — squarely inside the focus window.
    _schedule(page, title="midday work", start_min=720, duration_min=60)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="midday work")
    # The attribute is absent (not "false") on in-window blocks.
    expect(block).not_to_have_attribute("data-off-hours", "true")


# --- tooltip carries the off-hours note --------------------------------


@pytest.mark.e2e
def test_off_hours_block_title_attribute_includes_warning(page, live_server):
    _goto_future(page, live_server)
    _schedule(page, title="midnight oil", start_min=60, duration_min=30)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="midnight oil")
    title_attr = block.get_attribute("title") or ""
    assert "outside focus hours" in title_attr


# --- threshold edge cases -----------------------------------------------


@pytest.mark.e2e
def test_block_exactly_starting_at_8am_is_in_focus(page, live_server):
    """08:00 is the inclusive start of the focus window — no off-hours."""
    _goto_future(page, live_server)
    _schedule(page, title="on the dot", start_min=480, duration_min=60)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="on the dot")
    expect(block).not_to_have_attribute("data-off-hours", "true")


@pytest.mark.e2e
def test_block_ending_exactly_at_8pm_is_in_focus(page, live_server):
    """A 19:30–20:00 block ends *at* DAY_END_MIN — still in window."""
    _goto_future(page, live_server)
    _schedule(page, title="closing bell", start_min=1170, duration_min=30)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="closing bell")
    expect(block).not_to_have_attribute("data-off-hours", "true")
