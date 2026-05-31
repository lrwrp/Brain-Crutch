"""End-to-end: the focus queue (one task at a time).

The Queue overlay presents today's actionable tasks one at a time. A task
qualifies for the queue when it's due today/overdue or scheduled on today and
is neither snoozed nor already done today. Two actions drive it:

  - Complete → marks the task done, drops it, shows the next;
  - Skip     → sends the current task to the BACK of the queue (you cycle).

Draining the queue (or opening it with nothing to do) shows the "All clear"
empty state.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from playwright.sync_api import expect


def _today_iso() -> str:
    return _dt.date.today().isoformat()


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


def _open_queue(page):
    page.locator("#queue-btn").click()
    expect(page.locator("#queue-overlay")).to_be_visible()


# --- opening ---------------------------------------------------------------


@pytest.mark.e2e
def test_queue_opens_with_first_task_and_count(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="alpha", dueDate=_today_iso())
    _make_task(page, title="beta", dueDate=_today_iso())
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-state-running")).to_be_visible()
    # The "all clear" empty state must NOT leak in while a task is showing
    # (regression: an ID rule out-specificity'd `.queue-state.hidden`).
    expect(page.locator("#queue-state-empty")).to_be_hidden()
    expect(page.locator("#queue-progress")).to_have_text("2 left")
    # The current card shows one of the two due-today tasks.
    title = page.locator("#queue-title").text_content()
    assert title in ("alpha", "beta")


@pytest.mark.e2e
def test_empty_state_when_nothing_actionable(page, live_server):
    page.goto(live_server.url)
    # A task with no due date and no schedule is not "today-relevant".
    _make_task(page, title="someday")
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-state-empty")).to_be_visible()
    expect(page.locator("#queue-state-running")).to_be_hidden()
    expect(page.locator(".queue-empty-headline")).to_contain_text("All clear")


# --- complete --------------------------------------------------------------


@pytest.mark.e2e
def test_complete_advances_then_drains_to_empty(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="alpha", dueDate=_today_iso())
    _make_task(page, title="beta", dueDate=_today_iso())
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-progress")).to_have_text("2 left")

    page.locator("#queue-complete-btn").click()
    expect(page.locator("#queue-progress")).to_have_text("1 left")

    page.locator("#queue-complete-btn").click()
    # Both done → empty state.
    expect(page.locator("#queue-state-empty")).to_be_visible()


@pytest.mark.e2e
def test_completed_tasks_persist_after_reload(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="alpha", dueDate=_today_iso())
    _make_task(page, title="beta", dueDate=_today_iso())
    page.reload()

    _open_queue(page)
    page.locator("#queue-complete-btn").click()
    page.locator("#queue-complete-btn").click()
    expect(page.locator("#queue-state-empty")).to_be_visible()
    page.locator("#queue-exit-btn").click()

    page.reload()
    # Both fell into the Completed (N) disclosure on the Tasks tab.
    expect(page.locator("#tasks-completed-summary")).to_have_text("Completed (2)")


# --- skip ------------------------------------------------------------------


@pytest.mark.e2e
def test_skip_sends_to_back_and_cycles(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="alpha", dueDate=_today_iso())
    _make_task(page, title="beta", dueDate=_today_iso())
    page.reload()

    _open_queue(page)
    first = page.locator("#queue-title").text_content()

    page.locator("#queue-skip-btn").click()
    second = page.locator("#queue-title").text_content()
    assert second != first, "skip should advance to the other task"
    # Skip doesn't complete anything, so the count holds.
    expect(page.locator("#queue-progress")).to_have_text("2 left")

    page.locator("#queue-skip-btn").click()
    third = page.locator("#queue-title").text_content()
    assert third == first, "skipping past the back of the queue cycles around"


# --- keyboard + exit -------------------------------------------------------


@pytest.mark.e2e
def test_c_key_completes_current(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="alpha", dueDate=_today_iso())
    _make_task(page, title="beta", dueDate=_today_iso())
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-progress")).to_have_text("2 left")
    page.keyboard.press("c")
    expect(page.locator("#queue-progress")).to_have_text("1 left")


@pytest.mark.e2e
def test_escape_exits_queue(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="alpha", dueDate=_today_iso())
    page.reload()

    _open_queue(page)
    page.keyboard.press("Escape")
    expect(page.locator("#queue-overlay")).to_be_hidden()
