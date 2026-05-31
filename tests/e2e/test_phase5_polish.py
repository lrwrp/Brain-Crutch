"""End-to-end: Phase 5 polish (Tier 2 #6).

Three visual modifiers on the day-timeline + Tasks-tab:

1. Past blocks dim (today only, when block end is before now).
2. Tasks-tab subline shows ``.ti-rolled-over`` when the task was
   scheduled on a past day and isn't done for it.
3. Completed (non-recurring) tasks move out of the main Tasks list
   into a collapsed "Completed (N)" disclosure.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from playwright.sync_api import expect


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def _yesterday_iso() -> str:
    return (_dt.date.today() - _dt.timedelta(days=1)).isoformat()


def _create_task(page, **fields) -> str:
    return page.evaluate(
        """async (body) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            return (await r.json()).id;
        }""",
        fields,
    )


# --- 1. Past-block dim --------------------------------------------------


@pytest.mark.e2e
def test_block_scheduled_early_today_marked_past(page, live_server):
    """A block at 00:00–00:30 on today should be data-past after the
    timeline tick runs. Wall clock must be > 00:30 for this to hold;
    test the assumption explicitly so a 00:15-test-run failure makes
    the cause obvious rather than mysterious."""
    page.goto(live_server.url)
    now_min = page.evaluate(
        "() => { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }"
    )
    if now_min < 31:
        pytest.skip("can't verify past-block before 00:31 local")

    _create_task(
        page,
        title="early bird",
        schedule={"date": _today_iso(), "startMin": 0, "durationMin": 30},
    )
    page.reload()

    block = page.locator(".task-block").filter(has_text="early bird")
    expect(block).to_have_attribute("data-past", "true")


# --- 2. Rolled-over subline --------------------------------------------


@pytest.mark.e2e
def test_yesterday_scheduled_undone_task_shows_rolled_over(page, live_server):
    page.goto(live_server.url)
    _create_task(
        page,
        title="missed yesterday",
        schedule={"date": _yesterday_iso(), "startMin": 540, "durationMin": 30},
    )
    page.reload()

    row = page.locator(".triage-item").filter(has_text="missed yesterday")
    subline = row.locator(".ti-subline")
    expect(subline).to_have_count(1)
    # The subline carries the .ti-rolled-over modifier.
    expect(subline).to_have_class("ti-subline ti-rolled-over")


@pytest.mark.e2e
def test_today_scheduled_task_is_not_rolled_over(page, live_server):
    page.goto(live_server.url)
    _create_task(
        page,
        title="on time",
        schedule={"date": _today_iso(), "startMin": 540, "durationMin": 30},
    )
    page.reload()

    row = page.locator(".triage-item").filter(has_text="on time")
    subline = row.locator(".ti-subline")
    expect(subline).to_have_count(1)
    # Plain subline; no rolled-over modifier.
    expect(subline).not_to_have_class("ti-subline ti-rolled-over")


# --- 3. Completed disclosure -------------------------------------------


@pytest.mark.e2e
def test_done_non_recurring_task_moves_into_completed_disclosure(page, live_server):
    page.goto(live_server.url)
    _create_task(page, title="will be done")
    _create_task(page, title="stays open")
    page.reload()

    # Both rows start in the main list.
    expect(page.locator("#tasks-list .triage-item")).to_have_count(2)
    expect(page.locator("#tasks-completed-details")).to_be_hidden()

    # Mark "will be done" complete via the row's done toggle.
    done_row = page.locator(".triage-item").filter(has_text="will be done")
    done_row.locator(".ti-done .action-btn").click()

    # Main list now holds only the open task.
    expect(page.locator("#tasks-list .triage-item")).to_have_count(1)
    expect(
        page.locator("#tasks-list .triage-item").filter(has_text="stays open")
    ).to_have_count(1)
    # Completed disclosure visible with the right count.
    expect(page.locator("#tasks-completed-details")).to_be_visible()
    expect(page.locator("#tasks-completed-summary")).to_have_text("Completed (1)")
    # And the done task lives inside it.
    expect(
        page.locator("#tasks-completed-list .triage-item").filter(has_text="will be done")
    ).to_have_count(1)


@pytest.mark.e2e
def test_recurring_done_today_stays_in_main_list(page, live_server):
    """Recurring tasks aren't hidden by the Completed disclosure even when
    checked done today — the recurring affordance is "see today's status
    + re-complete tomorrow."""
    page.goto(live_server.url)
    _create_task(page, title="daily standup", recurring=True)
    page.reload()

    row = page.locator(".triage-item").filter(has_text="daily standup")
    row.locator(".ti-done .action-btn").click()

    # Recurring + done today → stays in the main list.
    expect(
        page.locator("#tasks-list .triage-item").filter(has_text="daily standup")
    ).to_have_count(1)
    # Completed disclosure stays hidden.
    expect(page.locator("#tasks-completed-details")).to_be_hidden()
