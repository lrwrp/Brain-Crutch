r"""End-to-end: the slash-command capture modal.

Each test starts on a fresh page against an isolated data dir, presses
``\`` then ``n`` (or ``t``), and verifies the modal opens, accepts input,
and saves to the right store.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_backslash_n_opens_inbox_modal_and_saves(page, live_server):
    page.goto(live_server.url)

    expect(page.locator("#capture-modal")).to_be_hidden()
    expect(page.locator("#inbox-count")).to_have_text("0")

    # Arm slash-mode, then trigger inbox.
    page.keyboard.press("Backslash")
    page.keyboard.press("n")

    modal = page.locator("#capture-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#capture-modal-title")).to_have_text("Capture to Inbox")

    modal_input = page.locator("#capture-modal-input")
    expect(modal_input).to_be_focused()
    modal_input.fill("remember the milk")
    modal_input.press("Enter")

    expect(modal).to_be_hidden()
    expect(page.locator("#inbox-count")).to_have_text("1")

    # Switch to the Inbox tab to verify the item shows up.
    page.locator('.tab[data-tab="inbox"]').click()
    inbox_items = page.locator("#inbox-list .triage-item")
    expect(inbox_items).to_have_count(1)
    expect(inbox_items.locator(".text")).to_contain_text("remember the milk")


@pytest.mark.e2e
def test_backslash_t_opens_task_modal_and_saves(page, live_server):
    page.goto(live_server.url)

    expect(page.locator("#tasks-count")).to_have_text("0")

    page.keyboard.press("Backslash")
    page.keyboard.press("t")

    modal = page.locator("#capture-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#capture-modal-title")).to_have_text("Create Task")

    modal_input = page.locator("#capture-modal-input")
    expect(modal_input).to_be_focused()
    modal_input.fill("Write the weekly report")
    modal_input.press("Enter")

    expect(modal).to_be_hidden()
    expect(page.locator("#tasks-count")).to_have_text("1")

    # Tasks tab is the default on a fresh page — task should be visible.
    task_rows = page.locator("#tasks-list .triage-item")
    expect(task_rows).to_have_count(1)
    expect(task_rows.locator(".text")).to_contain_text("Write the weekly report")


@pytest.mark.e2e
def test_escape_in_modal_cancels_without_saving(page, live_server):
    page.goto(live_server.url)

    page.keyboard.press("Backslash")
    page.keyboard.press("n")

    modal_input = page.locator("#capture-modal-input")
    expect(modal_input).to_be_focused()
    modal_input.fill("never to be saved")
    modal_input.press("Escape")

    expect(page.locator("#capture-modal")).to_be_hidden()
    expect(page.locator("#inbox-count")).to_have_text("0")


@pytest.mark.e2e
def test_shift_enter_inserts_newline_in_modal(page, live_server):
    """Shift+Enter must insert a newline; only plain Enter saves and closes."""
    page.goto(live_server.url)
    page.keyboard.press("Backslash")
    page.keyboard.press("n")

    modal_input = page.locator("#capture-modal-input")
    expect(modal_input).to_be_focused()
    modal_input.fill("first line")
    modal_input.press("Shift+Enter")

    # Modal still open — Shift+Enter didn't submit.
    expect(page.locator("#capture-modal")).to_be_visible()

    # And the value now has a newline.
    value = modal_input.input_value()
    assert "\n" in value, f"expected newline after Shift+Enter, got: {value!r}"
