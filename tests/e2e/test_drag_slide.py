"""End-to-end: drag-collision slide-past + W/S skip-past obstacle.

Tier 1 #3 / Phase 7 entry.

Behavior under test:
  - Dragging a block onto another block no longer reverts. The released
    position is taken as a hint; the block snaps to the nearest free slot.
  - W on a selected task that would collide upward skips past the obstacle
    to the next free slot above (and analogously for S downward).
  - When the day is genuinely full, drag still reverts (no silent loss).

Uses a far-future date (2099-06-15) so the free-slot search is deterministic
regardless of the wall-clock time when the test runs.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def _seed_two_abutting(page, *, date: str, a_title: str, b_title: str,
                       a_start: int, a_dur: int, b_dur: int) -> None:
    """POST two tasks scheduled on `date`: A at [a_start, a_start+a_dur),
    B immediately after at [a_start+a_dur, a_start+a_dur+b_dur). Reloads
    so the boot fetch picks them up."""
    page.evaluate(
        """async ([date, aTitle, bTitle, aStart, aDur, bDur]) => {
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: aTitle,
                    schedule: {date, startMin: aStart, durationMin: aDur}
                })
            });
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: bTitle,
                    schedule: {date, startMin: aStart + aDur, durationMin: bDur}
                })
            });
        }""",
        [date, a_title, b_title, a_start, a_dur, b_dur],
    )
    page.reload()
    # Jump the view to the seeded date.
    page.locator("#date-picker").evaluate(
        f"el => {{ el.value = '{date}'; el.dispatchEvent(new Event('change')); }}"
    )


@pytest.mark.e2e
def test_drag_over_obstacle_snaps_past(page, live_server):
    """A at 08:00-08:30; B at 08:30-09:00. Drag A down 30 px (release at
    08:30, exactly on B). With slide-past the release-into-overlap snaps
    to the next free position — 09:00 (past B)."""
    page.goto(live_server.url)
    _seed_two_abutting(
        page,
        date="2099-06-15",
        a_title="Block A",
        b_title="Block B",
        a_start=480,  # 08:00
        a_dur=30,
        b_dur=30,
    )

    block_a = page.locator(".task-block").filter(has_text="Block A")
    expect(block_a).to_be_visible()
    expect(block_a).to_have_attribute("data-start", "480")

    # Drag A's center down 30 px → release position would be startMin = 510,
    # which collides with B [510, 540). nearestFreeSlot returns 540.
    box = block_a.bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx, cy + 30, steps=5)
    page.mouse.up()

    expect(block_a).to_have_attribute("data-start", "540")
    # B stays put.
    expect(
        page.locator(".task-block").filter(has_text="Block B")
    ).to_have_attribute("data-start", "510")


@pytest.mark.e2e
def test_w_skips_past_obstacle_upward(page, live_server):
    """A at 08:30-09:15 (45m); B at 09:15-09:45 (30m) — abutting. Pressing W
    on B (delta = -15 → proposed 09:00) collides with A. Directional search
    walks backward past A and lands at the first free slot above A: 08:00."""
    page.goto(live_server.url)
    _seed_two_abutting(
        page,
        date="2099-06-15",
        a_title="Top A",
        b_title="Bottom B",
        a_start=510,  # 08:30
        a_dur=45,
        b_dur=30,
    )

    block_b = page.locator(".task-block").filter(has_text="Bottom B")
    expect(block_b).to_be_visible()
    expect(block_b).to_have_attribute("data-start", "555")

    # Select B then press W.
    block_b.click()
    expect(block_b).to_have_class(
        # selected class is appended; just check membership
        # (Playwright's to_have_class accepts a regex)
        __import__("re").compile(r"\bselected\b")
    )
    page.keyboard.press("w")

    expect(block_b).to_have_attribute("data-start", "480")
    expect(
        page.locator(".task-block").filter(has_text="Top A")
    ).to_have_attribute("data-start", "510")


@pytest.mark.e2e
def test_no_free_slot_drag_reverts(page, live_server):
    """Fill the day to within an inch of full, then drag a block onto an
    abutter so no nearestFreeSlot exists for it. The block reverts.

    Setup: one 720-minute block covers the entire day window (08:00–20:00).
    Add a second 30-minute block — but the day is already full, so the POST
    creates it unscheduled (no schedule set). To exercise drag-reverts,
    instead create A at 08:00-19:30 (690 min) and B at 19:30-20:00 (30 min).
    Then any drag of B that overlaps A has no free slot: the only free
    position is 19:30, which is where B already lives."""
    page.goto(live_server.url)
    page.evaluate(
        """async () => {
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: 'Fills A',
                    schedule: {date: '2099-06-15', startMin: 480, durationMin: 690}
                })
            });
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: 'Tiny B',
                    schedule: {date: '2099-06-15', startMin: 1170, durationMin: 30}
                })
            });
        }"""
    )
    page.reload()
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )

    block_b = page.locator(".task-block").filter(has_text="Tiny B")
    expect(block_b).to_be_visible()
    expect(block_b).to_have_attribute("data-start", "1170")

    # Drag B up 30 px (would put it at 1140, overlapping A). The only free
    # position fitting a 30-min block is 1170 itself, so nearestFreeSlot
    # returns that — which equals the original, meaning the move is a no-op.
    # The implementation snaps to that and reports the snap-toast; either way
    # the block ends up back at 1170.
    box = block_b.bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx, cy - 30, steps=5)
    page.mouse.up()

    expect(block_b).to_have_attribute("data-start", "1170")
