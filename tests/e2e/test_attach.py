"""End-to-end: attach an inbox item to a task via the picker."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_attach_inbox_item_to_existing_task(page, live_server):
    page.goto(live_server.url)

    # 1. Create an unscheduled task via the inline Tasks-tab input.
    page.locator("#task-input").fill("Read article")
    page.locator("#task-input").press("Enter")
    expect(page.locator("#tasks-list .triage-item")).to_have_count(1)

    # 2. Capture an inbox item via the slash modal. The form-submit handler
    #    now blurs the input on success, so the backslash keystroke routes
    #    to the document and arms slash-mode as expected.
    page.keyboard.press("Backslash")
    page.keyboard.press("n")
    modal_input = page.locator("#capture-modal-input")
    modal_input.fill("https://example.com/article")
    modal_input.press("Enter")

    # 3. Switch to the Inbox tab.
    page.locator('.tab[data-tab="inbox"]').click()
    inbox_item = page.locator("#inbox-list .triage-item")
    expect(inbox_item).to_have_count(1)

    # 4. Click Attach on the inbox item → picker opens.
    inbox_item.locator(".action-btn").filter(has_text="Attach").click()
    picker = page.locator(".attach-picker")
    expect(picker).to_be_visible()

    # 5. Picker contains our unscheduled task as an option.
    option = picker.locator(".attach-option").filter(has_text="Read article")
    expect(option).to_be_visible()

    # 6. Pick the task → attach happens, inbox empties.
    option.click()
    expect(page.locator("#inbox-count")).to_have_text("0")
    expect(page.locator("#inbox-list .triage-item")).to_have_count(0)

    # 7. Switch to Tasks tab; the task now has a notes indicator.
    page.locator('.tab[data-tab="tasks"]').click()
    task_row = page.locator("#tasks-list .triage-item").filter(has_text="Read article")
    expect(task_row.locator(".notes-icon")).to_be_visible()
