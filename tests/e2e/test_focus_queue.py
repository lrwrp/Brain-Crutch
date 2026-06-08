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
def test_empty_state_when_only_scheduled_tasks(page, live_server):
    """The queue is the *un-timed* pile. A task scheduled on today lives on the
    timeline, not the queue — so a day with only scheduled tasks is 'all clear'
    in the queue."""
    page.goto(live_server.url)
    _make_task(
        page,
        title="on the timeline",
        schedule={"date": _today_iso(), "startMin": 600, "durationMin": 30},
    )
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-state-empty")).to_be_visible()
    expect(page.locator("#queue-state-running")).to_be_hidden()
    expect(page.locator(".queue-empty-headline")).to_contain_text("All clear")


@pytest.mark.e2e
def test_scheduled_task_excluded_unscheduled_included(page, live_server):
    page.goto(live_server.url)
    _make_task(
        page,
        title="timed",
        schedule={"date": _today_iso(), "startMin": 540, "durationMin": 30},
    )
    _make_task(page, title="untimed")  # no schedule → queueable
    page.reload()

    _open_queue(page)
    # Only the un-timed task is in the queue.
    expect(page.locator("#queue-progress")).to_have_text("1 left")
    expect(page.locator("#queue-title")).to_have_text("untimed")


@pytest.mark.e2e
def test_card_shows_duration_size_cue(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="big one", defaultDurationMin=90)
    page.reload()

    _open_queue(page)
    # Un-timed tasks show a bucketed size cue; 90 min → "> 60".
    expect(page.locator("#queue-duration")).to_have_text("> 60")


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


# --- card stack: peek headers ---------------------------------------------


@pytest.mark.e2e
def test_peek_shows_next_task_title_and_size(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="next up", defaultDurationMin=90)  # older → upcoming
    _make_task(page, title="current")  # newest → active
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-title")).to_have_text("current")
    peeks = page.locator(".queue-peek-card")
    expect(peeks).to_have_count(1)
    expect(peeks.first.locator(".queue-peek-title")).to_have_text("next up")
    expect(peeks.first.locator(".queue-peek-dur")).to_have_text("> 60")


@pytest.mark.e2e
def test_peek_caps_with_plus_n_more(page, live_server):
    page.goto(live_server.url)
    for i in range(5):
        _make_task(page, title=f"t{i}")
    page.reload()

    _open_queue(page)
    # 5 tasks = 1 active + 4 upcoming; the peek caps at 3 + a "+1 more" tail.
    expect(page.locator(".queue-peek-card")).to_have_count(3)
    expect(page.locator(".queue-peek-more")).to_have_text("+1 more")


# --- notes on the active card ---------------------------------------------


@pytest.mark.e2e
def test_notes_button_opens_reader_over_queue(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="has notes", notes="remember the milk")
    page.reload()

    _open_queue(page)
    page.locator("#queue-notes-btn").click()
    expect(page.locator("#notes-read-modal")).to_be_visible()
    expect(page.locator("#notes-read-body")).to_contain_text("remember the milk")


@pytest.mark.e2e
def test_r_key_opens_notes_reader_in_queue(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="notesy", notes="hello there")
    page.reload()

    _open_queue(page)
    page.keyboard.press("r")
    expect(page.locator("#notes-read-modal")).to_be_visible()


# --- escape stack: notes ⇄ queue ------------------------------------------


@pytest.mark.e2e
def test_queue_read_then_escape_returns_to_queue(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="with notes", notes="some notes")
    page.reload()

    _open_queue(page)
    page.keyboard.press("r")
    expect(page.locator("#notes-read-modal")).to_be_visible()
    page.keyboard.press("Escape")
    # Reader closes; the queue is still up underneath (not closed).
    expect(page.locator("#notes-read-modal")).to_be_hidden()
    expect(page.locator("#queue-state-running")).to_be_visible()


@pytest.mark.e2e
def test_queue_edit_then_escape_returns_to_queue(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="edit me", notes="x")
    page.reload()

    _open_queue(page)
    page.keyboard.press("e")  # direct edit from the queue card
    expect(page.locator("#notes-modal")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#notes-modal")).to_be_hidden()
    expect(page.locator("#queue-state-running")).to_be_visible()


@pytest.mark.e2e
def test_queue_read_edit_escape_chain(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="chain", notes="hello")
    page.reload()

    _open_queue(page)
    page.keyboard.press("r")  # read
    expect(page.locator("#notes-read-modal")).to_be_visible()
    page.keyboard.press("e")  # edit (from reader)
    expect(page.locator("#notes-modal")).to_be_visible()
    expect(page.locator("#notes-read-modal")).to_be_hidden()
    page.keyboard.press("Escape")  # editor → back to read
    expect(page.locator("#notes-modal")).to_be_hidden()
    expect(page.locator("#notes-read-modal")).to_be_visible()
    page.keyboard.press("Escape")  # read → back to queue
    expect(page.locator("#notes-read-modal")).to_be_hidden()
    expect(page.locator("#queue-state-running")).to_be_visible()


@pytest.mark.e2e
def test_typing_in_queue_editor_does_not_fire_queue_keys(page, live_server):
    """While the editor is open over the queue, c/s type into the textarea
    instead of triggering complete/skip."""
    page.goto(live_server.url)
    _make_task(page, title="only one")
    page.reload()

    _open_queue(page)
    expect(page.locator("#queue-progress")).to_have_text("1 left")
    page.keyboard.press("e")  # editor opens (works even with no notes)
    inp = page.locator("#notes-modal-input")
    expect(inp).to_be_visible()
    inp.type("csc notes")
    expect(inp).to_have_value("csc notes")
    expect(page.locator("#notes-modal")).to_be_visible()


# --- un-timed recurrence (Stage 4) ----------------------------------------

_WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@pytest.mark.e2e
def test_untimed_recur_queues_only_on_matching_day(page, live_server):
    page.goto(live_server.url)
    today_tok = _WEEK[_dt.date.today().weekday()]
    other_tok = _WEEK[(_dt.date.today().weekday() + 1) % 7]
    # Un-timed recurs (no startMin): one lands today, one doesn't.
    _make_task(page, title="today recur", recurSchedule={"startMin": None, "days": [today_tok]})
    _make_task(page, title="offday recur", recurSchedule={"startMin": None, "days": [other_tok]})
    page.reload()

    _open_queue(page)
    # Only the matching-day recur is in the queue; the off-day one is hidden.
    expect(page.locator("#queue-progress")).to_have_text("1 left")
    expect(page.locator("#queue-title")).to_have_text("today recur")


@pytest.mark.e2e
def test_recur_popover_no_specific_time_makes_untimed(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="make me untimed")
    page.reload()

    # Open the recur popover from the task row, tick "No specific time", Every day.
    page.locator("#tasks-list .triage-item .ti-recurring").first.click()
    page.locator(".recur-menu .recur-notime").check()
    page.locator(".recur-menu .recur-option", has_text="Every day").click()

    page.wait_for_function(
        """async () => {
            const d = await (await fetch('/api/tasks')).json();
            const rs = d.items[0].recurSchedule;
            return rs && rs.startMin === null && rs.durationMin === null;
        }"""
    )
