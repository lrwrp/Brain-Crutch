"""End-to-end: Escape closes the inline attach picker."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_escape_closes_attach_picker(page, live_server):
    page.goto(live_server.url)

    # Give the picker something to show.
    page.locator("#task-input").fill("target task")
    page.locator("#task-input").press("Enter")
    expect(page.locator("#tasks-list .triage-item")).to_have_count(1)

    # Capture an inbox item via the modal. The form-submit handler blurs
    # the input on success, so the backslash keystroke routes to the document.
    page.keyboard.press("Backslash")
    page.keyboard.press("n")
    modal_input = page.locator("#capture-modal-input")
    modal_input.fill("a thought")
    modal_input.press("Enter")

    # Switch to Inbox and open the attach picker.
    page.locator('.tab[data-tab="inbox"]').click()
    inbox_item = page.locator("#inbox-list .triage-item").first
    inbox_item.locator(".action-btn").filter(has_text="Attach").click()

    picker = page.locator(".attach-picker")
    expect(picker).to_be_visible()

    # Esc closes the picker (modal isn't open, so Esc routes to picker close).
    page.keyboard.press("Escape")
    expect(page.locator(".attach-picker")).to_have_count(0)
