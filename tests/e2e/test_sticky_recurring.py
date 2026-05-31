"""End-to-end: sticky-time recurring (Tier 2 #15).

A task carrying a ``recurSchedule`` projects onto the timeline at the same
time on every matching day, without a per-day schedule write. The projection
is display-only (dashed ``data-sticky="true"`` block) until the user
drags/edits it. These tests exercise the projection rules end-to-end:

  - every-day (days=null) projects onto today;
  - a weekday set projects on a weekday and is absent on Saturday;
  - a date in recurExceptions suppresses the projection;
  - the ↻ popover writes a recurSchedule that immediately projects;
  - removing a projected block via the row arrow adds an exception.

Seeding writes ``tasks.json`` in the per-test data dir directly (the server
doesn't accept recurSchedule any differently than via PATCH, but writing the
file is the simplest way to stand up a specific cadence). storage upgrades
the file to the current version and _normalize_task fills the rest on read.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

# Sunday-indexed? No — server/storage tokens are mon..sun. Python's
# date.weekday() is Mon=0..Sun=6, which lines up with this list directly.
WEEKDAY_TOKENS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS = WEEKDAY_TOKENS[:5]


def _next_weekday(start: datetime.date, weekday_idx: int) -> datetime.date:
    d = start
    while d.weekday() != weekday_idx:
        d += datetime.timedelta(days=1)
    return d


# A fixed far-future anchor keeps these dates clear of "today" coincidences.
_ANCHOR = datetime.date(2099, 1, 1)
MONDAY = _next_weekday(_ANCHOR, 0).isoformat()
SATURDAY = _next_weekday(_ANCHOR, 5).isoformat()


def _seed(data_dir: Path, items: list[dict]) -> None:
    path = data_dir / "tasks.json"
    path.write_text(json.dumps({"version": 3, "items": items}))


def _recur_task(
    *,
    id: str,
    title: str,
    start_min: int = 540,  # 09:00
    duration_min: int = 30,
    days: list[str] | None = None,
    exceptions: list[str] | None = None,
) -> dict:
    return {
        "id": id,
        "title": title,
        "priority": "medium",
        "done": False,
        "completedAt": None,
        "createdAt": 0,
        "updatedAt": 0,
        "tags": [],
        "defaultDurationMin": duration_min,
        "schedule": None,
        "notes": None,
        "dueDate": None,
        "recurring": True,
        "snoozedUntil": None,
        "deletedAt": None,
        "recurSchedule": {
            "startMin": start_min,
            "durationMin": duration_min,
            "days": days,
        },
        "recurExceptions": list(exceptions or []),
    }


def _goto_date(page, date_str: str) -> None:
    page.locator("#date-picker").evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('change')); }",
        date_str,
    )
    expect(page.locator("#date-picker")).to_have_value(date_str)


def _sticky(page, title: str):
    return page.locator(".task-block[data-sticky='true']").filter(has_text=title)


# --- projection rules ----------------------------------------------------


@pytest.mark.e2e
def test_every_day_projects_onto_today(page, live_server):
    _seed(
        live_server.data_dir,
        [_recur_task(id="r1", title="every day standup", days=None)],
    )
    page.goto(live_server.url)
    # Default day is today; an every-day cadence lands a sticky block.
    expect(_sticky(page, "every day standup")).to_have_count(1)


@pytest.mark.e2e
def test_weekday_recur_projects_on_a_weekday(page, live_server):
    _seed(
        live_server.data_dir,
        [_recur_task(id="r2", title="weekday focus", days=WEEKDAYS)],
    )
    page.goto(live_server.url)
    _goto_date(page, MONDAY)
    expect(_sticky(page, "weekday focus")).to_have_count(1)


@pytest.mark.e2e
def test_weekday_recur_absent_on_saturday(page, live_server):
    _seed(
        live_server.data_dir,
        [_recur_task(id="r3", title="weekday focus", days=WEEKDAYS)],
    )
    page.goto(live_server.url)
    _goto_date(page, SATURDAY)
    expect(_sticky(page, "weekday focus")).to_have_count(0)


@pytest.mark.e2e
def test_exception_suppresses_projection(page, live_server):
    # Every-day cadence, but MONDAY is listed as a skip.
    _seed(
        live_server.data_dir,
        [
            _recur_task(
                id="r4", title="skippable", days=None, exceptions=[MONDAY]
            )
        ],
    )
    page.goto(live_server.url)

    # MONDAY: suppressed by the exception.
    _goto_date(page, MONDAY)
    expect(_sticky(page, "skippable")).to_have_count(0)

    # The next day (Tuesday) has no exception → block is back.
    tuesday = (datetime.date.fromisoformat(MONDAY) + datetime.timedelta(days=1)).isoformat()
    _goto_date(page, tuesday)
    expect(_sticky(page, "skippable")).to_have_count(1)


# --- popover writes a recurSchedule --------------------------------------


@pytest.mark.e2e
def test_recur_popover_every_day_creates_projection(page, live_server):
    page.goto(live_server.url)
    # Create a plain one-shot task via API, then make it sticky via the ↻
    # popover. The time input defaults to 09:00, so clicking "Every day"
    # lands a sticky block on today.
    page.evaluate(
        """async () => {
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: 'make me sticky'})
            });
        }"""
    )
    page.reload()

    row = page.locator(".triage-item").filter(has_text="make me sticky")
    row.locator(".ti-recurring").click()
    menu = page.locator(".recur-menu")
    expect(menu).to_be_visible()
    menu.locator(".recur-time-input").fill("09:00")
    menu.locator(".recur-option", has_text="Every day").click()

    expect(_sticky(page, "make me sticky")).to_have_count(1)


@pytest.mark.e2e
def test_recur_popover_stop_repeating_removes_projection(page, live_server):
    _seed(
        live_server.data_dir,
        [_recur_task(id="r5", title="kill the loop", days=None)],
    )
    page.goto(live_server.url)
    expect(_sticky(page, "kill the loop")).to_have_count(1)

    row = page.locator(".triage-item").filter(has_text="kill the loop")
    row.locator(".ti-recurring").click()
    menu = page.locator(".recur-menu")
    expect(menu).to_be_visible()
    menu.locator(".recur-option", has_text="Stop repeating").click()

    expect(_sticky(page, "kill the loop")).to_have_count(0)


# --- removing a projected block via the row arrow ------------------------


@pytest.mark.e2e
def test_row_arrow_removes_projected_block_via_exception(page, live_server):
    _seed(
        live_server.data_dir,
        [_recur_task(id="r6", title="arrow skip", days=None)],
    )
    page.goto(live_server.url)
    expect(_sticky(page, "arrow skip")).to_have_count(1)

    # The row arrow reads "scheduled" for a projected-today task; clicking it
    # adds today to recurExceptions, removing the projection for today only.
    row = page.locator(".triage-item").filter(has_text="arrow skip")
    arrow = row.locator(".ti-arrow")
    expect(arrow).to_have_attribute("data-state", "scheduled")
    arrow.click()

    expect(_sticky(page, "arrow skip")).to_have_count(0)
