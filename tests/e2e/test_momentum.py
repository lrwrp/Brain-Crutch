"""End-to-end: the momentum gauge + activity mosaic.

A forgiving replacement for the streak. A topbar ember reflects recent use;
the stats modal shows a gauge + a last-~10-weeks mosaic. Activity is logged
per day (open check-in + meaningful actions) via /api/activity.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_topbar_ember_present_and_has_level(page, live_server):
    page.goto(live_server.url)
    ember = page.locator("#momentum-ember")
    expect(ember).to_be_visible()
    # initMomentum sets a numeric level (0-4) on boot.
    level = ember.get_attribute("data-level")
    assert level in {"0", "1", "2", "3", "4"}


@pytest.mark.e2e
def test_stats_modal_shows_gauge_and_mosaic(page, live_server):
    page.goto(live_server.url)
    page.locator("#momentum-ember").click()  # ember opens the modal too
    expect(page.locator("#stats-modal")).to_be_visible()
    expect(page.locator(".momentum-gauge")).to_be_visible()
    # Mosaic renders a grid of day cells (10ish weeks × 7 rows).
    cells = page.locator(".momentum-mosaic .mosaic-cell")
    assert cells.count() >= 70
    # The retired streak line must be gone.
    expect(page.locator(".stats-streak")).to_have_count(0)


@pytest.mark.e2e
def test_opening_the_app_records_a_checkin(page, live_server):
    page.goto(live_server.url)
    # The boot check-in pings /api/activity once for today; poll until it lands.
    page.wait_for_function(
        """async () => {
            const r = await fetch('/api/activity');
            const d = await r.json();
            return Object.values(d.days || {}).reduce((a, b) => a + b, 0) >= 1;
        }"""
    )


@pytest.mark.e2e
def test_completing_a_task_adds_activity(page, live_server):
    page.goto(live_server.url)

    # Create a task via the API, then reload so it renders in the Tasks tab.
    page.evaluate(
        """async () => {
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: 'momentum task'})
            });
        }"""
    )
    page.reload()

    def total_activity():
        return page.evaluate(
            """async () => {
                const r = await fetch('/api/activity');
                const d = await r.json();
                return Object.values(d.days || {}).reduce((a, b) => a + b, 0);
            }"""
        )

    # Wait out the boot check-in first so the baseline is stable.
    page.wait_for_function(
        """async () => {
            const r = await fetch('/api/activity');
            const d = await r.json();
            return Object.values(d.days || {}).reduce((a, b) => a + b, 0) >= 1;
        }"""
    )
    before = total_activity()

    # Complete the task via its Tasks-tab done toggle.
    page.locator('.tab[data-tab="tasks"]').click()
    row = page.locator("#tasks-list .triage-item", has_text="momentum task")
    row.locator(".ti-done .action-btn").click()

    # The debounced ping (≤400ms) should raise the day's total.
    page.wait_for_function(
        """(before) => (async () => {
            const r = await fetch('/api/activity');
            const d = await r.json();
            const t = Object.values(d.days || {}).reduce((a, b) => a + b, 0);
            return t > before;
        })()""",
        arg=before,
    )
