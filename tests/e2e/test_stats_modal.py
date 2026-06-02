"""End-to-end: wins stats modal (Tier 2 #8).

Click ``#wins`` → modal opens with five tabs (Today / Week / Month /
Year / All-time). Each tab shows a total, a priority breakdown
(⭐/●/○), and the momentum gauge + activity mosaic (full-history,
window-independent).

For tabs beyond Today, seeding requires arbitrary ``completedAt``
timestamps. The server doesn't accept completedAt via POST or PATCH
(it's server-stamped), so the tests write to ``tasks.json`` in the
per-test ``live_server.data_dir`` and then page.reload() to pick the
seed up — much simpler than building a test-only endpoint.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect


def _seed_tasks(data_dir: Path, items: list[dict]) -> None:
    """Write ``items`` directly into the per-test tasks.json. Each item
    must already have the schema-v2 shape (id, title, done, completedAt,
    etc.). storage's _normalize_task fills in the rest on read."""
    path = data_dir / "tasks.json"
    path.write_text(json.dumps({"version": 2, "items": items}))


def _task(
    *,
    id: str,
    title: str,
    completed_at: float,
    priority: str = "medium",
) -> dict:
    return {
        "id": id,
        "title": title,
        "priority": priority,
        "done": True,
        "completedAt": completed_at,
        "createdAt": completed_at,
        "updatedAt": completed_at,
        "tags": [],
        "defaultDurationMin": 30,
        "schedule": None,
        "notes": None,
        "dueDate": None,
        "recurring": False,
        "snoozedUntil": None,
        "deletedAt": None,
    }


# --- modal open / close --------------------------------------------------


@pytest.mark.e2e
def test_clicking_wins_opens_modal(page, live_server):
    page.goto(live_server.url)
    expect(page.locator("#stats-modal")).to_be_hidden()
    page.locator("#wins").click()
    expect(page.locator("#stats-modal")).to_be_visible()
    # Default tab is Today.
    expect(
        page.locator(".stats-tab[data-window='today']")
    ).to_have_class("stats-tab active")


@pytest.mark.e2e
def test_escape_closes_modal(page, live_server):
    page.goto(live_server.url)
    page.locator("#wins").click()
    expect(page.locator("#stats-modal")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#stats-modal")).to_be_hidden()


@pytest.mark.e2e
def test_backdrop_click_closes_modal(page, live_server):
    page.goto(live_server.url)
    page.locator("#wins").click()
    expect(page.locator("#stats-modal")).to_be_visible()
    # Click a corner — the backdrop's bounding-box center lies on top
    # of .modal-content, which doesn't have a close handler, so
    # Playwright's default center-click reports a click intercept.
    page.locator("#stats-modal .modal-backdrop").click(position={"x": 5, "y": 5})
    expect(page.locator("#stats-modal")).to_be_hidden()


# --- today tab matches the wins pill -------------------------------------


@pytest.mark.e2e
def test_today_tab_total_matches_wins_pill(page, live_server):
    page.goto(live_server.url)

    # Two highs, one medium completed today via API (POST stamps completedAt).
    for title, prio in [("a", "high"), ("b", "high"), ("c", "medium")]:
        page.evaluate(
            """async ([title, priority]) => {
                await fetch('/api/tasks', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({title, priority, done: true})
                });
            }""",
            [title, prio],
        )
    page.reload()

    expect(page.locator("#wins")).to_contain_text("✓ 3 today")
    page.locator("#wins").click()
    expect(page.locator(".stats-total")).to_have_text("✓ 3 completed")
    expect(page.locator(".stats-prio-high")).to_have_text("⭐ 2")
    expect(page.locator(".stats-prio-medium")).to_have_text("● 1")
    expect(page.locator(".stats-prio-low")).to_have_text("○ 0")


# --- window switching with seeded older data ----------------------------


@pytest.mark.e2e
def test_all_time_includes_older_completions_today_does_not(page, live_server):
    now = time.time()
    # 1 today, 1 ten days ago, 1 a year ago.
    _seed_tasks(
        live_server.data_dir,
        [
            _task(id="t0", title="today's win", completed_at=now, priority="high"),
            _task(id="t10", title="10-day-old", completed_at=now - 10 * 86400, priority="low"),
            _task(id="t365", title="ancient", completed_at=now - 365 * 86400, priority="medium"),
        ],
    )
    page.goto(live_server.url)
    page.locator("#wins").click()

    # Today: just the fresh one.
    expect(page.locator(".stats-total")).to_have_text("✓ 1 completed")
    expect(page.locator(".stats-prio-high")).to_have_text("⭐ 1")

    # Week: today + the 10-day-old? 10 days > 7-day window — so just 1.
    page.locator(".stats-tab[data-window='week']").click()
    expect(page.locator(".stats-total")).to_have_text("✓ 1 completed")

    # Month: 30-day window — picks up today + the 10-day-old, not the 365-day.
    page.locator(".stats-tab[data-window='month']").click()
    expect(page.locator(".stats-total")).to_have_text("✓ 2 completed")

    # Year: 365-day rolling. The "ancient" task is right at the boundary;
    # because we computed `now - 365*86400` and the cutoff is the same,
    # it may or may not be included depending on subsecond drift between
    # the test setup and the modal render. Don't assert a hard count here
    # — just that the total is at least the month total.
    page.locator(".stats-tab[data-window='year']").click()
    year_text = page.locator(".stats-total").text_content() or ""
    assert "✓ 2 completed" in year_text or "✓ 3 completed" in year_text

    # All-time: every record.
    page.locator(".stats-tab[data-window='all']").click()
    expect(page.locator(".stats-total")).to_have_text("✓ 3 completed")
    expect(page.locator(".stats-prio-high")).to_have_text("⭐ 1")
    expect(page.locator(".stats-prio-medium")).to_have_text("● 1")
    expect(page.locator(".stats-prio-low")).to_have_text("○ 1")


# --- momentum (replaced the streak line) ---------------------------------


@pytest.mark.e2e
def test_modal_shows_momentum_and_no_streak(page, live_server):
    """The streak line is gone; the modal now shows the momentum gauge +
    mosaic instead."""
    page.goto(live_server.url)
    page.locator("#wins").click()
    expect(page.locator(".momentum-gauge")).to_be_visible()
    expect(page.locator(".momentum-mosaic")).to_be_visible()
    expect(page.locator(".stats-streak")).to_have_count(0)


# --- live update on TASK_CHANGED bus event ------------------------------


@pytest.mark.e2e
def test_completion_landing_after_open_updates_total_live(page, live_server):
    """The stats body subscribes to TASK_* bus events so a completion that
    lands while the modal is open updates without reopen. The modal
    intercepts pointer events page-wide, so the test closes the modal,
    clicks the done toggle, reopens — the Today total carries the new
    count. (A purely-open path would need the bus from outside the modal,
    which the live page can't reach via UI; the subscription is proven
    indirectly by wins.js's live-tick test.)"""
    page.goto(live_server.url)
    page.evaluate(
        """async () => {
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: 'will be done after open'})
            });
        }"""
    )
    page.reload()

    page.locator("#wins").click()
    expect(page.locator(".stats-total")).to_have_text("✓ 0 completed")
    page.keyboard.press("Escape")

    row = page.locator(".triage-item").filter(has_text="will be done after open")
    row.locator(".ti-done .action-btn").click()
    expect(page.locator("#wins")).to_contain_text("✓ 1 today")

    page.locator("#wins").click()
    expect(page.locator(".stats-total")).to_have_text("✓ 1 completed")
