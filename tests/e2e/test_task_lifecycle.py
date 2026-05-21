"""End-to-end: make a task, schedule it on today, unschedule it.

These tests cover the path users live in most: tasks tab → arrow →
timeline, and the inverse (arrow → off the timeline). Tier 2 #12
replaced the labeled "Today" / "Off today" buttons with a single
`.ti-arrow` whose `data-state` flips between "unscheduled" and
"scheduled".
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_make_task_via_inline_input(page, live_server):
    page.goto(live_server.url)

    task_input = page.locator("#task-input")
    task_input.fill("Pick up groceries")
    task_input.press("Enter")

    task_row = page.locator("#tasks-list .triage-item").filter(
        has_text="Pick up groceries"
    )
    expect(task_row).to_be_visible()
    # No schedule yet — arrow shows the unscheduled state.
    expect(task_row.locator(".ti-arrow")).to_have_attribute(
        "data-state", "unscheduled"
    )
    # And no block on the timeline yet.
    expect(page.locator(".task-block")).to_have_count(0)


@pytest.mark.e2e
def test_today_button_schedules_task_on_timeline(page, live_server):
    page.goto(live_server.url)

    # Create an unscheduled task.
    page.locator("#task-input").fill("Pick up groceries")
    page.locator("#task-input").press("Enter")

    task_row = page.locator("#tasks-list .triage-item").filter(
        has_text="Pick up groceries"
    )

    # Click the arrow — currently shows the "unscheduled" state.
    arrow = task_row.locator(".ti-arrow")
    expect(arrow).to_have_attribute("data-state", "unscheduled")
    arrow.click()

    # Task row now sports a schedule sub-line (day + start time).
    expect(task_row.locator(".ti-subline")).to_contain_text("Today")

    # Arrow flips to "scheduled" state.
    expect(arrow).to_have_attribute("data-state", "scheduled")

    # A matching block appears on the timeline.
    block = page.locator(".task-block").filter(has_text="Pick up groceries")
    expect(block).to_be_visible()


@pytest.mark.e2e
def test_inline_submit_blurs_input_so_slash_command_works(page, live_server):
    """Regression for Tier 1 #2 — the inline #task-input used to re-focus
    itself after submit, swallowing the next `\\n` / `\\t` keystroke. With
    the fix, the input blurs on success so the slash command arms via the
    document handler."""
    page.goto(live_server.url)

    page.locator("#task-input").fill("first task")
    page.locator("#task-input").press("Enter")
    expect(page.locator("#tasks-list .triage-item")).to_have_count(1)

    # No manual blur — the input should already have released focus.
    page.keyboard.press("Backslash")
    page.keyboard.press("t")
    expect(page.locator("#capture-modal")).to_be_visible()


@pytest.mark.e2e
def test_inline_submit_with_empty_input_keeps_focus(page, live_server):
    """An empty submit is a no-op (the handler returns early). Focus should
    stay in the input so the user can keep typing — important because the
    blur-on-success path is gated on a successful create."""
    page.goto(live_server.url)
    inp = page.locator("#task-input")
    inp.click()
    inp.press("Enter")  # nothing typed
    # Focused element is still the task input.
    focused_id = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused_id == "task-input"


@pytest.mark.e2e
def test_arrow_unschedules_task(page, live_server):
    """Click the arrow once → scheduled. Click again → unscheduled.
    Replaces the old chip-× pattern; the arrow is now the sole control."""
    page.goto(live_server.url)

    # Create + schedule via the arrow.
    page.locator("#task-input").fill("Pay the bills")
    page.locator("#task-input").press("Enter")
    task_row = page.locator("#tasks-list .triage-item").filter(
        has_text="Pay the bills"
    )
    arrow = task_row.locator(".ti-arrow")
    arrow.click()  # → scheduled

    expect(arrow).to_have_attribute("data-state", "scheduled")
    expect(task_row.locator(".ti-subline")).to_contain_text("Today")
    block = page.locator(".task-block").filter(has_text="Pay the bills")
    expect(block).to_be_visible()

    # Click the arrow again → unscheduled.
    arrow.click()

    expect(arrow).to_have_attribute("data-state", "unscheduled")
    expect(task_row.locator(".ti-subline")).to_have_count(0)
    expect(task_row).to_be_visible()
    expect(page.locator(".task-block").filter(has_text="Pay the bills")).to_have_count(
        0
    )
