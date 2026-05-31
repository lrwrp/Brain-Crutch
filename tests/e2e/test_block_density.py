"""End-to-end: timeline block density tiers (Tier 2 #13).

A task block's inner layout degrades as duration shrinks so a 30-min block
stays readable and a 15-min block at least shows its title. The picker is
``data-density="comfy" | "compact" | "tiny"`` set by ``applyBlockGeometry``
at 45 and 25 min thresholds.

Tests use a far-future date (2099-06-15) so wall-clock has no influence
and tasks can be placed at predictable times.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


FUTURE = "2099-06-15"


def _schedule(page, *, title: str, start_min: int, duration_min: int) -> None:
    page.evaluate(
        """async (body) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            return r.ok;
        }""",
        {
            "title": title,
            "schedule": {
                "date": FUTURE,
                "startMin": start_min,
                "durationMin": duration_min,
            },
        },
    )


def _goto_future(page, live_server) -> None:
    page.goto(live_server.url)
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")


# --- density mapping ----------------------------------------------------


@pytest.mark.e2e
def test_60_min_block_is_comfy(page, live_server):
    _goto_future(page, live_server)
    _schedule(page, title="hour-long task", start_min=540, duration_min=60)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="hour-long task")
    expect(block).to_have_attribute("data-density", "comfy")
    # Meta row still visible at comfy.
    expect(block.locator(".task-meta")).to_be_visible()


@pytest.mark.e2e
def test_30_min_block_is_compact(page, live_server):
    _goto_future(page, live_server)
    _schedule(page, title="half-hour task", start_min=600, duration_min=30)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="half-hour task")
    expect(block).to_have_attribute("data-density", "compact")


@pytest.mark.e2e
def test_15_min_block_is_tiny_and_hides_meta(page, live_server):
    _goto_future(page, live_server)
    _schedule(page, title="quarter-hour", start_min=660, duration_min=15)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="quarter-hour")
    expect(block).to_have_attribute("data-density", "tiny")
    # Meta row is display:none at tiny.
    expect(block.locator(".task-meta")).to_be_hidden()


# --- threshold edge cases -----------------------------------------------


@pytest.mark.e2e
def test_45_min_block_is_comfy_not_compact(page, live_server):
    """At exactly the 45-min threshold the comfy layout still applies."""
    _goto_future(page, live_server)
    _schedule(page, title="just barely comfy", start_min=540, duration_min=45)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="just barely comfy")
    expect(block).to_have_attribute("data-density", "comfy")


@pytest.mark.e2e
def test_25_min_block_is_compact_not_tiny(page, live_server):
    """At exactly the 25-min threshold the compact layout still applies."""
    _goto_future(page, live_server)
    _schedule(page, title="barely compact", start_min=540, duration_min=25)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="barely compact")
    expect(block).to_have_attribute("data-density", "compact")


# --- tooltip carries full time info -------------------------------------


@pytest.mark.e2e
def test_tiny_block_carries_schedule_in_native_tooltip(page, live_server):
    """At tiny density the meta is hidden, so the start–end range moves to
    the block's title attribute (browser-native tooltip)."""
    _goto_future(page, live_server)
    _schedule(page, title="short thing", start_min=600, duration_min=15)
    page.reload()
    page.locator("#date-picker").fill(FUTURE)
    page.locator("#date-picker").press("Enter")

    block = page.locator(".task-block").filter(has_text="short thing")
    title_attr = block.get_attribute("title") or ""
    assert "short thing" in title_attr
    assert "10:00" in title_attr  # 600 min
    assert "10:15" in title_attr  # 600 + 15
    assert "15m" in title_attr
