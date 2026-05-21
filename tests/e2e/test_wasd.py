"""End-to-end: click-to-select on a task, then WASD keyboard actions.

W/S move a scheduled task ±15 min on the timeline. A/D adjust priority on
any selected task.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_click_block_selects_and_s_shifts_start_15_minutes(page, live_server):
    page.goto(live_server.url)

    # Far-future date gives the task room to move down without clamping.
    page.locator("#date-picker").evaluate(
        "el => { el.value = '2099-06-15'; el.dispatchEvent(new Event('change')); }"
    )

    # Create a scheduled task via + task.
    page.locator("#add-task").click()
    modal_input = page.locator("#capture-modal-input")
    expect(modal_input).to_be_focused()
    modal_input.fill("WASD target")
    modal_input.press("Enter")

    block = page.locator(".task-block").filter(has_text="WASD target")
    expect(block).to_be_visible()
    original_start = int(block.get_attribute("data-start"))

    # Click without dragging → selection.
    block.click()
    expect(block).to_have_class(re.compile(r"\bselected\b"))

    # S key moves the block +15 min.
    page.keyboard.press("s")
    expect(block).to_have_attribute("data-start", str(original_start + 15))


@pytest.mark.e2e
def test_a_lowers_priority_on_selected_task(page, live_server):
    page.goto(live_server.url)

    page.locator("#task-input").fill("Lower me")
    page.locator("#task-input").press("Enter")
    task_row = page.locator("#tasks-list .triage-item").filter(has_text="Lower me")

    # Click the title text (not the stripe or buttons) to select.
    task_row.locator(".text").click()
    expect(task_row).to_have_class(re.compile(r"\bselected\b"))

    # Default is medium; A steps down to low.
    expect(task_row).to_have_attribute("data-priority", "medium")
    page.keyboard.press("a")
    expect(task_row).to_have_attribute("data-priority", "low")
