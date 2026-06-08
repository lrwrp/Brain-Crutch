"""End-to-end: the L / M duration control (Stage 1 of the granularity epic).

Every task row carries a ‹ Nm › stepper showing its exact duration. The
keyboard `L` / `M` keys (on the selected task) and the chip's ‹ / › buttons
both step it on the 5-minute ladder: … 5, 10, … with a sub-5 "< 5" floor
(stored as 1 → shown "1m" in triage) and open-ended growth. Un-timed tasks
edit `defaultDurationMin`; the value persists server-side.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def _make_task(page, title: str = "size me", **fields) -> str:
    body = {"title": title, **fields}
    return page.evaluate(
        """async (b) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(b)
            });
            return (await r.json()).id;
        }""",
        body,
    )


def _wait_default_duration(page, value: int) -> None:
    """Wait for the (debounced) server write to land on `value`."""
    page.wait_for_function(
        """async (v) => {
            const r = await fetch('/api/tasks');
            const d = await r.json();
            return d.items[0].defaultDurationMin === v;
        }""",
        arg=value,
    )


@pytest.mark.e2e
def test_row_shows_exact_duration(page, live_server):
    page.goto(live_server.url)
    _make_task(page)
    page.reload()
    row = page.locator("#tasks-list .triage-item").first
    # New tasks default to 30 min; triage shows the full value, not a bucket.
    expect(row.locator(".ti-dur-val")).to_have_text("30m")


@pytest.mark.e2e
def test_m_and_l_keys_step_duration_on_selected_task(page, live_server):
    page.goto(live_server.url)
    _make_task(page)
    page.reload()

    row = page.locator("#tasks-list .triage-item").first
    row.locator(".ti-title .text").click()  # select it (click the title text)

    page.keyboard.press("m")  # 30 -> 35
    expect(page.locator("#tasks-list .triage-item").first.locator(".ti-dur-val")).to_have_text("35m")

    page.keyboard.press("l")  # 35 -> 30
    page.keyboard.press("l")  # 30 -> 25
    expect(page.locator("#tasks-list .triage-item").first.locator(".ti-dur-val")).to_have_text("25m")

    _wait_default_duration(page, 25)


@pytest.mark.e2e
def test_chip_steppers_adjust_and_persist(page, live_server):
    page.goto(live_server.url)
    _make_task(page, title="tap me")
    page.reload()

    row = page.locator("#tasks-list .triage-item").first
    # nth(0) = ‹ (less), nth(1) = › (more)
    row.locator(".ti-dur-step").nth(1).click()  # 30 -> 35
    expect(page.locator("#tasks-list .triage-item").first.locator(".ti-dur-val")).to_have_text("35m")
    _wait_default_duration(page, 35)


@pytest.mark.e2e
def test_less_floors_at_sub_five_bucket(page, live_server):
    page.goto(live_server.url)
    _make_task(page)
    page.reload()

    row = page.locator("#tasks-list .triage-item").first
    row.locator(".ti-title .text").click()
    # 30 -> 25 -> 20 -> 15 -> 10 -> 5 -> 1, then floored at 1.
    for _ in range(8):
        page.keyboard.press("l")
    expect(page.locator("#tasks-list .triage-item").first.locator(".ti-dur-val")).to_have_text("1m")
    _wait_default_duration(page, 1)
