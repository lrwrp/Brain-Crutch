"""End-to-end: 24-hour timeline canvas (Tier 2 #5 / Phase 7).

Two-window model:
  - The timeline canvas spans the full 24 hours so the user can drag late-night
    and pre-dawn tasks freely.
  - Auto-scheduling (Today button / + task) still constrains to the 08:00-20:00
    focus window so the bot never places a task at 03:00 by surprise.

Default scroll puts 08:00 near the top with ~30 min of pre-dawn visible above.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_hour_labels_span_full_24_hours(page, live_server):
    page.goto(live_server.url)
    labels = page.locator("#hours .hour-label")
    # 00:00 through 23:00 inclusive = 24 labels.
    expect(labels).to_have_count(24)
    expect(labels.first).to_have_text("00:00")
    expect(labels.last).to_have_text("23:00")


@pytest.mark.e2e
def test_canvas_is_1440px_tall(page, live_server):
    page.goto(live_server.url)
    # 1 px per minute * 1440 min = 1440 px.
    tracks_height = page.evaluate(
        "document.querySelector('#tracks').getBoundingClientRect().height"
    )
    assert tracks_height == pytest.approx(1440, abs=1), (
        f"expected tracks canvas to be 1440px tall, got {tracks_height}"
    )


@pytest.mark.e2e
def test_initial_scroll_anchors_focus_window(page, live_server):
    """The timeline should default-scroll so 07:30 sits at the top of the
    visible area (i.e. scrollTop ≈ 450)."""
    page.goto(live_server.url)
    # Wait a beat for layout + initTimeline's scrollToFocus to run.
    page.wait_for_function(
        "document.querySelector('#timeline').scrollTop >= 449"
    )
    scroll_top = page.evaluate(
        "document.querySelector('#timeline').scrollTop"
    )
    assert scroll_top == pytest.approx(450, abs=1), (
        f"expected default scroll ≈ 450 (07:30 at top), got {scroll_top}"
    )


@pytest.mark.e2e
def test_can_schedule_off_hours_via_manual_API(page, live_server):
    """A task explicitly scheduled at 03:00 renders as a normal block —
    the 24h canvas accommodates it."""
    page.goto(live_server.url)
    page.evaluate(
        """async () => {
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: 'Late night task',
                    schedule: {date: '2099-06-15', startMin: 180, durationMin: 30}
                })
            });
        }"""
    )
    page.reload()
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )
    block = page.locator(".task-block").filter(has_text="Late night task")
    expect(block).to_be_visible()
    expect(block).to_have_attribute("data-start", "180")


@pytest.mark.e2e
def test_auto_schedule_still_lands_in_focus_window(page, live_server):
    """The + task / Today button must still bias to 08:00-20:00. Empty day →
    new task lands at 08:00, not at 00:00."""
    page.goto(live_server.url)
    # Jump to a future date so findFreeSlot starts at DAY_START_MIN (not "now").
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )
    page.locator("#add-task").click()
    modal_input = page.locator("#capture-modal-input")
    modal_input.fill("Future-day task")
    modal_input.press("Enter")

    block = page.locator(".task-block").filter(has_text="Future-day task")
    expect(block).to_be_visible()
    expect(block).to_have_attribute("data-start", "480")  # 08:00, not 00:00
