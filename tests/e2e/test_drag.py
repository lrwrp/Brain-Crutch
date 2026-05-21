"""End-to-end: drag a timeline block to reschedule it.

Uses a far-future date so the new task lands at 08:00 (DAY_START) regardless
of when the test runs — gives the block headroom to drag downward without
hitting the day-end clamp.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_dragging_block_down_30px_shifts_start_30_minutes(page, live_server):
    page.goto(live_server.url)

    # Jump to a date where findFreeSlot always returns DAY_START.
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )

    # Create a scheduled task via the + task modal.
    page.locator("#add-task").click()
    modal_input = page.locator("#capture-modal-input")
    expect(modal_input).to_be_focused()
    modal_input.fill("Drag me")
    modal_input.press("Enter")

    block = page.locator(".task-block").filter(has_text="Drag me")
    expect(block).to_be_visible()
    original_start = int(block.get_attribute("data-start"))
    assert original_start == 480, f"expected DAY_START (480), got {original_start}"

    # Drag from the block's center down by 30 px (= 30 min @ 1 px/min).
    box = block.bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx, cy + 30, steps=5)
    page.mouse.up()

    # Snap on a 30-px (multiple of 15) delta lands exactly on +30.
    expect(block).to_have_attribute("data-start", str(original_start + 30))
