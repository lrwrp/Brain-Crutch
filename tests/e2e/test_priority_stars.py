"""End-to-end: priority stars on the wins counter (Tier 2 #7).

One ⭐ per high-priority completion today. Medium and low still feed the
total `✓ N today` count but earn no star. Stars render on a single row
(up to 10 visible); past that a `+N` overflow tag closes the row.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def _make_task(page, title: str, *, priority: str = "medium") -> str:
    """Create a task via the API. Returns its id."""
    return page.evaluate(
        """async ([title, priority]) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title, priority})
            });
            const data = await r.json();
            return data.id;
        }""",
        [title, priority],
    )


def _mark_done_today(page, task_id: str) -> None:
    """PATCH `done: true` so the server stamps a fresh completedAt."""
    page.evaluate(
        """async ([id]) => {
            await fetch(`/api/tasks/${id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({done: true})
            });
        }""",
        [task_id],
    )


# --- Single-star cases ----------------------------------------------------


@pytest.mark.e2e
def test_no_high_priority_done_means_no_star_block(page, live_server):
    """Completing only medium/low tasks → count goes up but #wins-stars
    has zero rows (the empty container collapses via CSS :empty)."""
    page.goto(live_server.url)
    tid = _make_task(page, "Medium done", priority="medium")
    _mark_done_today(page, tid)
    page.reload()

    expect(page.locator("#wins")).to_contain_text("✓ 1 today")
    expect(page.locator("#wins-stars .wins-row")).to_have_count(0)


@pytest.mark.e2e
def test_one_high_done_renders_one_star(page, live_server):
    page.goto(live_server.url)
    tid = _make_task(page, "High done", priority="high")
    _mark_done_today(page, tid)
    page.reload()

    expect(page.locator("#wins")).to_contain_text("✓ 1 today")
    rows = page.locator("#wins-stars .wins-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_text("⭐")


# --- Row wrap ------------------------------------------------------------


@pytest.mark.e2e
def test_five_highs_fill_one_row(page, live_server):
    page.goto(live_server.url)
    for i in range(5):
        _mark_done_today(page, _make_task(page, f"high {i}", priority="high"))
    page.reload()

    rows = page.locator("#wins-stars .wins-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_text("⭐⭐⭐⭐⭐")
    expect(page.locator("#wins")).to_contain_text("✓ 5 today")


@pytest.mark.e2e
def test_seven_highs_stay_on_one_row(page, live_server):
    page.goto(live_server.url)
    for i in range(7):
        _mark_done_today(page, _make_task(page, f"high {i}", priority="high"))
    page.reload()

    rows = page.locator("#wins-stars .wins-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_text("⭐⭐⭐⭐⭐⭐⭐")


# --- Overflow ------------------------------------------------------------


@pytest.mark.e2e
def test_overflow_indicator_past_the_cap(page, live_server):
    page.goto(live_server.url)
    for i in range(13):
        _mark_done_today(page, _make_task(page, f"high {i}", priority="high"))
    page.reload()

    rows = page.locator("#wins-stars .wins-row")
    expect(rows).to_have_count(1)
    # 10 stars visible, then a +3 overflow tag on the same row.
    expect(rows.first).to_contain_text("⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐")
    expect(rows.first.locator(".wins-overflow")).to_have_text("+3")
    expect(page.locator("#wins")).to_contain_text("✓ 13 today")


# --- Mixed priority ------------------------------------------------------


@pytest.mark.e2e
def test_only_high_priority_completions_get_stars(page, live_server):
    """3 high + 2 medium + 1 low all done today: total reads 6, stars = 3."""
    page.goto(live_server.url)
    for i in range(3):
        _mark_done_today(page, _make_task(page, f"H{i}", priority="high"))
    for i in range(2):
        _mark_done_today(page, _make_task(page, f"M{i}", priority="medium"))
    _mark_done_today(page, _make_task(page, "L", priority="low"))
    page.reload()

    expect(page.locator("#wins")).to_contain_text("✓ 6 today")
    rows = page.locator("#wins-stars .wins-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_text("⭐⭐⭐")


# --- Live update via bus -------------------------------------------------


@pytest.mark.e2e
def test_clicking_done_toggle_on_high_adds_a_star_live(page, live_server):
    """Toggle done on a high-priority task via the UI — TASK_CHANGED on the
    bus rerenders the wins block with a fresh star."""
    page.goto(live_server.url)
    _make_task(page, "Important", priority="high")
    page.reload()

    expect(page.locator("#wins")).to_contain_text("✓ 0 today")
    expect(page.locator("#wins-stars .wins-row")).to_have_count(0)

    page.locator("#tasks-list .triage-item").first.locator(
        ".ti-done .action-btn"
    ).click()

    expect(page.locator("#wins")).to_contain_text("✓ 1 today")
    expect(page.locator("#wins-stars .wins-row")).to_have_text("⭐")


# --- Tooltip carries the priority breakdown ------------------------------


@pytest.mark.e2e
def test_wins_title_carries_high_priority_count(page, live_server):
    page.goto(live_server.url)
    for i in range(2):
        _mark_done_today(page, _make_task(page, f"H{i}", priority="high"))
    _mark_done_today(page, _make_task(page, "M", priority="medium"))
    page.reload()

    expect(page.locator("#wins")).to_have_attribute(
        "title", "3 completed today (2 high-priority)"
    )
