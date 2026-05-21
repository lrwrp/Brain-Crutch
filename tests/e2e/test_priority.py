"""End-to-end: priority stripe click cycle + Tasks-tab sort ordering."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_clicking_stripe_cycles_priority(page, live_server):
    page.goto(live_server.url)

    page.locator("#task-input").fill("Cycle me")
    page.locator("#task-input").press("Enter")

    task_row = page.locator("#tasks-list .triage-item").filter(has_text="Cycle me")
    expect(task_row).to_have_attribute("data-priority", "medium")

    stripe = task_row.locator(".priority-stripe")

    # medium → high
    stripe.click()
    expect(task_row).to_have_attribute("data-priority", "high")

    # high → low (cycle wraps)
    stripe.click()
    expect(task_row).to_have_attribute("data-priority", "low")

    # low → medium
    stripe.click()
    expect(task_row).to_have_attribute("data-priority", "medium")


@pytest.mark.e2e
def test_high_priority_sorts_above_medium_in_tasks_tab(page, live_server):
    page.goto(live_server.url)

    # Create two tasks (both default to medium).
    for title in ("First", "Second"):
        page.locator("#task-input").fill(title)
        page.locator("#task-input").press("Enter")

    # Promote "Second" to high.
    second_row = page.locator("#tasks-list .triage-item").filter(has_text="Second")
    second_row.locator(".priority-stripe").click()
    expect(second_row).to_have_attribute("data-priority", "high")

    # The Tasks tab section sorts high above medium.
    titles = page.locator("#tasks-list .triage-item .text")
    expect(titles.nth(0)).to_have_text("Second")
    expect(titles.nth(1)).to_have_text("First")
