"""End-to-end: Undo toast restores soft-deleted items.

Covers Phase 4.7 A1: deleting an inbox item or a task pops a persistent toast
with an Undo button. Clicking Undo calls the server's ``/restore`` endpoint
and the item reappears in its tab.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_undo_restores_deleted_inbox_item(page, live_server):
    page.goto(live_server.url)

    # Capture an inbox item via the slash modal.
    page.keyboard.press("Backslash")
    page.keyboard.press("n")
    modal_input = page.locator("#capture-modal-input")
    modal_input.fill("undoable thought")
    modal_input.press("Enter")
    expect(page.locator("#inbox-count")).to_have_text("1")

    # Switch to Inbox and click ×.
    page.locator('.tab[data-tab="inbox"]').click()
    inbox_item = page.locator("#inbox-list .triage-item")
    expect(inbox_item).to_have_count(1)
    inbox_item.locator(".action-btn.danger").click()

    # Item is gone; Undo toast is visible.
    expect(page.locator("#inbox-list .triage-item")).to_have_count(0)
    toast = page.locator("#toast")
    expect(toast).to_be_visible()
    expect(toast.locator(".toast-text")).to_contain_text("undoable thought")
    undo = toast.locator(".toast-undo")
    expect(undo).to_be_visible()

    # Click Undo → item reappears.
    undo.click()
    expect(page.locator("#inbox-list .triage-item")).to_have_count(1)
    expect(page.locator("#inbox-count")).to_have_text("1")


@pytest.mark.e2e
def test_undo_restores_deleted_task(page, live_server):
    page.goto(live_server.url)

    # Create a task via the inline Tasks-tab input.
    page.locator("#task-input").fill("undoable task")
    page.locator("#task-input").press("Enter")
    expect(page.locator("#tasks-list .triage-item")).to_have_count(1)

    # Click × on the task row.
    task_row = page.locator("#tasks-list .triage-item").first
    task_row.locator(".action-btn.danger").click()

    # Task gone; Undo toast visible.
    expect(page.locator("#tasks-list .triage-item")).to_have_count(0)
    toast = page.locator("#toast")
    expect(toast).to_be_visible()
    expect(toast.locator(".toast-text")).to_contain_text("undoable task")

    # Undo → task reappears in Tasks tab.
    toast.locator(".toast-undo").click()
    expect(page.locator("#tasks-list .triage-item")).to_have_count(1)


@pytest.mark.e2e
def test_undo_toast_close_button_dismisses_without_restoring(page, live_server):
    """Clicking × on the toast just hides it — the soft-delete stays."""
    page.goto(live_server.url)

    page.keyboard.press("Backslash")
    page.keyboard.press("n")
    page.locator("#capture-modal-input").fill("close-me")
    page.locator("#capture-modal-input").press("Enter")
    expect(page.locator("#inbox-count")).to_have_text("1")

    page.locator('.tab[data-tab="inbox"]').click()
    page.locator("#inbox-list .triage-item").first.locator(".action-btn.danger").click()

    toast = page.locator("#toast")
    expect(toast).to_be_visible()
    toast.locator(".toast-close").click()

    # Toast hidden (clearToast strips children + removes .show), inbox still
    # empty (item remains soft-deleted server-side).
    expect(toast.locator(".toast-text")).to_have_count(0)
    expect(page.locator("#inbox-list .triage-item")).to_have_count(0)
    expect(page.locator("#inbox-count")).to_have_text("0")
