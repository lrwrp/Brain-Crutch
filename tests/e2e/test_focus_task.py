"""End-to-end: focus-mode task binding (granularity epic #25, Stage 5).

During a running focus session, the task whose block sits under the now-line is
surfaced as a card with Snooze / Complete + notes. Nothing scheduled for the
current moment → no card.

The preroll is real-time (3 seconds), so each test waits through it to reach the
running state (mirrors test_focus_timer).
"""

from __future__ import annotations

import datetime as _dt

import pytest
from playwright.sync_api import expect


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def _now_min() -> int:
    n = _dt.datetime.now()
    return n.hour * 60 + n.minute


def _make_task(page, **fields) -> str:
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


def _schedule_now(start_offset: int = -5, duration: int = 120) -> dict:
    """A schedule window that contains the current minute, clamped to >= 0."""
    start = max(0, _now_min() + start_offset)
    return {"date": _today_iso(), "startMin": start, "durationMin": duration}


def _start_focus(page):
    """Open the launcher and run the preroll out to the running state."""
    page.locator("#focus-btn").click()
    page.locator("#focus-minutes").press("Enter")
    page.wait_for_selector("#focus-state-running:not(.hidden)", timeout=4500)


# --- binding --------------------------------------------------------------


@pytest.mark.e2e
def test_focus_binds_current_timeline_task(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="write report", schedule=_schedule_now())
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_visible()
    expect(page.locator("#focus-task-title")).to_have_text("write report")


@pytest.mark.e2e
def test_no_card_when_nothing_scheduled_now(page, live_server):
    page.goto(live_server.url)
    # A task scheduled well clear of now (early morning) — not under the now-line.
    _make_task(
        page,
        title="early bird",
        schedule={"date": _today_iso(), "startMin": 0, "durationMin": 30},
    )
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_hidden()


@pytest.mark.e2e
def test_unscheduled_task_does_not_bind(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="queue thing")  # un-timed → lives in the queue
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_hidden()


# --- complete -------------------------------------------------------------


@pytest.mark.e2e
def test_complete_bound_task_hides_card_and_bumps_wins(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="finish me", schedule=_schedule_now())
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_visible()

    page.locator("#focus-task-complete-btn").click()
    # The task is done → no longer the current timeline task → card hides.
    expect(page.locator("#focus-task")).to_be_hidden()
    # Still in the running session (we didn't cancel).
    expect(page.locator("#focus-state-running")).to_be_visible()
    # The completion counted as a win.
    expect(page.locator("#wins")).to_contain_text("✓ 1 today")


@pytest.mark.e2e
def test_c_key_completes_bound_task(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="keyed done", schedule=_schedule_now())
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_visible()

    page.keyboard.press("c")
    expect(page.locator("#focus-task")).to_be_hidden()
    expect(page.locator("#wins")).to_contain_text("✓ 1 today")


# --- snooze ---------------------------------------------------------------


@pytest.mark.e2e
def test_snooze_bound_task_hides_card(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="not now", schedule=_schedule_now())
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_visible()

    page.locator("#focus-snooze-btn").click()
    menu = page.locator(".snooze-menu")
    expect(menu).to_be_visible()
    menu.locator(".snooze-option").first.click()
    # Snoozed → cleared from today's timeline → card hides.
    expect(page.locator("#focus-task")).to_be_hidden()
    expect(page.locator("#focus-state-running")).to_be_visible()


# --- notes ----------------------------------------------------------------


@pytest.mark.e2e
def test_notes_reader_opens_from_focus_card(page, live_server):
    page.goto(live_server.url)
    _make_task(
        page,
        title="with notes",
        notes="remember the milk",
        schedule=_schedule_now(),
    )
    page.reload()

    _start_focus(page)
    expect(page.locator("#focus-task")).to_be_visible()

    page.keyboard.press("r")
    expect(page.locator("#notes-read-modal")).to_be_visible()
    expect(page.locator("#notes-read-modal")).to_contain_text("remember the milk")
