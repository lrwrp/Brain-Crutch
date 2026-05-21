"""End-to-end: Tier 2 #12 task row redesign.

Covers the new affordances that came in with the slot-grid rework:
  - Arrow bar (← / →) for scheduling on/off today's timeline
  - Snooze popover with preset durations
  - "Snoozed (N)" disclosure at the bottom of the Tasks tab
  - Recurring icon (↻) for tasks flagged `recurring: true`
  - Due-date display, formatted by urgency
"""

from __future__ import annotations

import datetime as _dt
import time as _time

import pytest
from playwright.sync_api import expect


def _make_task(page, **fields) -> str:
    """Create a task with the given fields via the API. Returns id."""
    body = {"title": fields.pop("title", "Untitled"), **fields}
    return page.evaluate(
        """async (body) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            return (await r.json()).id;
        }""",
        body,
    )


# --- Arrow ---------------------------------------------------------------


@pytest.mark.e2e
def test_arrow_default_state_is_unscheduled(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="No schedule")
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="No schedule")
    arrow = row.locator(".ti-arrow")
    expect(arrow).to_have_attribute("data-state", "unscheduled")
    expect(arrow).to_have_text("‹")


@pytest.mark.e2e
def test_arrow_click_schedules_today_and_flips(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="To today")
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="To today")
    arrow = row.locator(".ti-arrow")
    arrow.click()

    expect(arrow).to_have_attribute("data-state", "scheduled")
    expect(arrow).to_have_text("›")
    # Schedule sub-line appears below the title.
    expect(row.locator(".ti-subline")).to_contain_text("Today")


# --- Snooze --------------------------------------------------------------


@pytest.mark.e2e
def test_snooze_button_opens_popover_with_presets(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="snooze me")
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="snooze me")
    row.locator(".ti-snooze .action-btn").click()

    menu = page.locator(".snooze-menu")
    expect(menu).to_be_visible()
    # All five presets present.
    options = menu.locator(".snooze-option")
    expect(options).to_have_count(5)
    expect(options.nth(0)).to_have_text("1 hour")
    expect(options.nth(1)).to_have_text("Until end of day")


@pytest.mark.e2e
def test_picking_snooze_hides_task_and_shows_in_snoozed_disclosure(
    page, live_server
):
    page.goto(live_server.url)
    _make_task(page, title="see you later")
    page.reload()

    # Snooze for 1 hour.
    page.locator("#tasks-list .triage-item").first.locator(
        ".ti-snooze .action-btn"
    ).click()
    page.locator(".snooze-option").filter(has_text="1 hour").click()

    # Main list empty; details disclosure visible with count 1.
    expect(page.locator("#tasks-list .triage-item")).to_have_count(0)
    details = page.locator("#tasks-snoozed-details")
    expect(details).to_be_visible()
    expect(page.locator("#tasks-snoozed-summary")).to_have_text("Snoozed (1)")

    # Expand and verify the row shows there, plus the "asleep until" sub-line.
    details.locator("summary").click()
    snoozed_row = page.locator("#tasks-snoozed-list .triage-item").filter(
        has_text="see you later"
    )
    expect(snoozed_row).to_be_visible()
    expect(snoozed_row.locator(".ti-wake")).to_contain_text("asleep until")


@pytest.mark.e2e
def test_snoozing_a_scheduled_task_clears_today_block(page, live_server):
    """Snoozing a task that's on today's timeline should also drop it from
    the timeline — sending it to bed reclaims the slot."""
    page.goto(live_server.url)
    _make_task(page, title="busy now")
    page.reload()

    # Schedule it onto today via the arrow.
    row = page.locator("#tasks-list .triage-item").filter(has_text="busy now")
    row.locator(".ti-arrow").click()
    block = page.locator(".task-block").filter(has_text="busy now")
    expect(block).to_be_visible()

    # Snooze it for 1 hour.
    row.locator(".ti-snooze .action-btn").click()
    page.locator(".snooze-option").filter(has_text="1 hour").click()

    # Block is gone, row is gone from the main list, snoozed disclosure
    # shows 1.
    expect(
        page.locator(".task-block").filter(has_text="busy now")
    ).to_have_count(0)
    expect(page.locator("#tasks-list .triage-item")).to_have_count(0)
    expect(page.locator("#tasks-snoozed-summary")).to_have_text("Snoozed (1)")


@pytest.mark.e2e
def test_wake_now_restores_to_main_list(page, live_server):
    page.goto(live_server.url)
    tid = _make_task(page, title="wake test")
    # Pre-snooze via API for 1 hour.
    page.evaluate(
        """async ([id]) => {
            const t = Math.floor(Date.now() / 1000) + 3600;
            await fetch(`/api/tasks/${id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({snoozedUntil: t})
            });
        }""",
        [tid],
    )
    page.reload()

    # Expand snoozed list, click "Wake now".
    page.locator("#tasks-snoozed-details summary").click()
    page.locator("#tasks-snoozed-list .triage-item").filter(
        has_text="wake test"
    ).locator(".ti-snooze .action-btn").click()

    # Row returns to the main list; details disclosure hides.
    expect(
        page.locator("#tasks-list .triage-item").filter(has_text="wake test")
    ).to_be_visible()
    expect(page.locator("#tasks-snoozed-details")).to_be_hidden()


# --- Recurring -----------------------------------------------------------


@pytest.mark.e2e
def test_recurring_icon_renders_bright(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="piano practice", recurring=True)
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(
        has_text="piano practice"
    )
    recur = row.locator(".ti-recurring")
    expect(recur).to_have_text("↻")
    expect(recur).to_have_attribute("data-recurring", "true")


@pytest.mark.e2e
def test_non_recurring_shows_muted_recurring_glyph(page, live_server):
    """The ↻ slot now always renders the glyph; the data-recurring attribute
    is the source of truth (`false` = muted, `true` = bright). Mirrors how
    the delete × sits muted at rest until hovered."""
    page.goto(live_server.url)
    _make_task(page, title="one-shot")
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="one-shot")
    recur = row.locator(".ti-recurring")
    expect(recur).to_have_text("↻")
    expect(recur).to_have_attribute("data-recurring", "false")


@pytest.mark.e2e
def test_clicking_recurring_slot_toggles_flag(page, live_server):
    """Click ↻ → recurring on; click again → off. Updates round-trip via
    PATCH so a reload preserves the new state."""
    page.goto(live_server.url)
    _make_task(page, title="toggleable")
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="toggleable")
    recur = row.locator(".ti-recurring")
    expect(recur).to_have_attribute("data-recurring", "false")

    recur.click()
    expect(recur).to_have_attribute("data-recurring", "true")

    # Persist across reload.
    page.reload()
    row = page.locator("#tasks-list .triage-item").filter(has_text="toggleable")
    expect(row.locator(".ti-recurring")).to_have_attribute(
        "data-recurring", "true"
    )

    # And back off.
    row.locator(".ti-recurring").click()
    expect(row.locator(".ti-recurring")).to_have_attribute(
        "data-recurring", "false"
    )


# --- Due date ------------------------------------------------------------


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def _days_from_now_iso(n: int) -> str:
    return (_dt.date.today() + _dt.timedelta(days=n)).isoformat()


@pytest.mark.e2e
def test_due_today_renders_red(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="due now", dueDate=_today_iso())
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="due now")
    due = row.locator(".due-date")
    expect(due).to_have_text("DUE TODAY")
    expect(due).to_have_class("due-date due-today")


@pytest.mark.e2e
def test_due_tomorrow_renders_yellow(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="due tmrw", dueDate=_days_from_now_iso(1))
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="due tmrw")
    due = row.locator(".due-date")
    expect(due).to_have_text("due tomorrow")
    expect(due).to_have_class("due-date due-soon")


@pytest.mark.e2e
def test_due_far_future_uses_month_day_format(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="future", dueDate=_days_from_now_iso(14))
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="future")
    due = row.locator(".due-date")
    expect(due).to_contain_text("due ")
    expect(due).to_have_class("due-date due-future")


@pytest.mark.e2e
def test_overdue_renders_red(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="overdue", dueDate=_days_from_now_iso(-2))
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="overdue")
    due = row.locator(".due-date")
    expect(due).to_have_text("OVERDUE")
    expect(due).to_have_class("due-date due-overdue")


@pytest.mark.e2e
def test_no_due_date_means_empty_due_slot(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="open-ended")
    page.reload()

    row = page.locator("#tasks-list .triage-item").filter(has_text="open-ended")
    # Slot present, no .due-date child.
    expect(row.locator(".ti-due .due-date")).to_have_count(0)
