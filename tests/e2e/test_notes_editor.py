"""End-to-end: Markdown notes — read view, edit view, keyboard shortcuts.

Phase 4.9 C3 split the original single-modal editor into:
  - A read modal that renders sanitized Markdown (opened by clicking 📝 or
    pressing `r` on the selected task)
  - An edit modal with a source-only textarea (opened by clicking the
    reader's [Edit] button or pressing `e` on the selected task)
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def _make_task_with_notes(page, *, title: str, notes: str | None) -> None:
    """Create a single unscheduled task and patch its notes via the API.

    Reload after the PATCH so the client's boot fetch picks up the seeded
    state (the client doesn't auto-poll the server).
    """
    page.keyboard.press("Backslash")
    page.keyboard.press("t")
    page.locator("#capture-modal-input").fill(title)
    page.locator("#capture-modal-input").press("Enter")
    if notes is not None:
        page.evaluate(
            """async ([notes]) => {
                const tasks = await fetch('/api/tasks').then(r => r.json());
                const t = tasks.items[0];
                await fetch(`/api/tasks/${t.id}`, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({notes})
                });
            }""",
            [notes],
        )
        page.reload()


# --- Reader (📝 click) ------------------------------------------------------


@pytest.mark.e2e
def test_clicking_notes_icon_opens_reader_with_rendered_markdown(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(
        page,
        title="Reader test",
        notes="## Plan\n- write **bold** text",
    )

    icon = page.locator("#tasks-list .triage-item .notes-icon").first
    expect(icon).to_be_visible()
    icon.click()

    reader = page.locator("#notes-read-modal")
    expect(reader).to_be_visible()
    # The editor modal stays hidden — we're in read mode.
    expect(page.locator("#notes-modal")).to_be_hidden()

    body = page.locator("#notes-read-body")
    expect(body.locator("h2")).to_have_text("Plan")
    expect(body.locator("strong")).to_have_text("bold")


@pytest.mark.e2e
def test_reader_edit_button_hands_off_to_editor(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="Handoff test", notes="starter content")

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    expect(page.locator("#notes-read-modal")).to_be_visible()

    page.locator("#notes-read-edit-btn").click()

    expect(page.locator("#notes-read-modal")).to_be_hidden()
    expect(page.locator("#notes-modal")).to_be_visible()
    # Editor populated with the same task's notes.
    expect(page.locator("#notes-modal-input")).to_have_value("starter content")


@pytest.mark.e2e
def test_reader_close_button_dismisses(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="Close test", notes="anything")

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    reader = page.locator("#notes-read-modal")
    expect(reader).to_be_visible()

    # The close button has aria-label="Close".
    reader.locator('[aria-label="Close"]').click()
    expect(reader).to_be_hidden()


@pytest.mark.e2e
def test_escape_in_reader_closes(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="Esc test", notes="anything")

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    page.keyboard.press("Escape")
    expect(page.locator("#notes-read-modal")).to_be_hidden()


# --- Sanitization (read view renders, so XSS surface is here) ---------------


@pytest.mark.e2e
def test_script_tag_in_notes_is_escaped_in_reader(page, live_server):
    """A <script> in the Markdown source must never become a live DOM
    script in the reader body."""
    page.goto(live_server.url)
    _make_task_with_notes(
        page,
        title="XSS test",
        notes="Hello <script>window.PWNED=true</script> world",
    )

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    body = page.locator("#notes-read-body")
    expect(body).to_contain_text("<script>")  # literal text
    assert body.locator("script").count() == 0
    assert page.evaluate("window.PWNED") is None, "sanitizer let a script run"


@pytest.mark.e2e
def test_disallowed_link_protocol_renders_as_text(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(
        page,
        title="Link safety",
        notes="[click me](javascript:alert(1)) and [docs](https://example.com)",
    )

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    body = page.locator("#notes-read-body")

    anchors = body.locator("a")
    expect(anchors).to_have_count(1)
    expect(anchors).to_have_attribute("href", "https://example.com")
    expect(body).to_contain_text("javascript:alert(1)")


# --- Editor (entered via [Edit] button or `e` shortcut) --------------------


@pytest.mark.e2e
def test_editor_enter_saves_persists_and_closes(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="Save test", notes="placeholder")

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    page.locator("#notes-read-edit-btn").click()

    modal_input = page.locator("#notes-modal-input")
    modal_input.fill("### Final notes\n- ship it")
    modal_input.press("Enter")

    expect(page.locator("#notes-modal")).to_be_hidden()
    expect(page.locator("#notes-read-modal")).to_be_hidden()

    # Poll the server until the PATCH has landed. Under heavy suite load
    # the modal-hidden state can be observed before the PATCH response is
    # fully written, so reading /api/tasks once-and-asserting flakes.
    page.wait_for_function(
        """async () => {
            const tasks = await fetch('/api/tasks').then(r => r.json());
            return tasks.items[0].notes === '### Final notes\\n- ship it';
        }""",
        timeout=5000,
    )


@pytest.mark.e2e
def test_editor_escape_cancels_without_saving(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="Cancel test", notes="original")

    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    page.locator("#notes-read-edit-btn").click()

    modal_input = page.locator("#notes-modal-input")
    modal_input.fill("changed — but cancelled")
    modal_input.press("Escape")

    expect(page.locator("#notes-modal")).to_be_hidden()
    persisted = page.evaluate(
        """async () => {
            const tasks = await fetch('/api/tasks').then(r => r.json());
            return tasks.items[0].notes;
        }"""
    )
    assert persisted == "original"


# --- r / e keyboard shortcuts on selected task ----------------------------


@pytest.mark.e2e
def test_r_on_selected_task_with_notes_opens_reader(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="r-shortcut", notes="some content")

    # Select the row by clicking its text (not the action buttons / stripe).
    page.locator("#tasks-list .triage-item").first.locator(".text").click()
    expect(page.locator("#tasks-list .triage-item.selected")).to_have_count(1)

    page.keyboard.press("r")
    expect(page.locator("#notes-read-modal")).to_be_visible()
    expect(page.locator("#notes-read-body")).to_contain_text("some content")


@pytest.mark.e2e
def test_r_on_task_with_no_notes_is_noop_toast(page, live_server):
    page.goto(live_server.url)
    _make_task_with_notes(page, title="no-notes task", notes=None)

    page.locator("#tasks-list .triage-item").first.locator(".text").click()
    expect(page.locator("#tasks-list .triage-item.selected")).to_have_count(1)

    page.keyboard.press("r")
    # Reader stays hidden; user gets the "no notes yet" toast instead.
    expect(page.locator("#notes-read-modal")).to_be_hidden()
    expect(page.locator("#toast")).to_contain_text("No notes yet")


@pytest.mark.e2e
def test_e_on_selected_task_opens_editor_even_without_notes(page, live_server):
    """`e` is also the 'start writing notes' affordance, so it must work on
    a task that has no notes yet."""
    page.goto(live_server.url)
    _make_task_with_notes(page, title="empty-notes task", notes=None)

    page.locator("#tasks-list .triage-item").first.locator(".text").click()
    expect(page.locator("#tasks-list .triage-item.selected")).to_have_count(1)

    page.keyboard.press("e")
    expect(page.locator("#notes-modal")).to_be_visible()
    expect(page.locator("#notes-modal-input")).to_have_value("")


@pytest.mark.e2e
def test_e_in_reader_hands_off_to_editor(page, live_server):
    """When the reader is open (from a 📝 click that didn't select the task),
    `e` should still open the editor for that task via the reader's tracked
    activeTaskId."""
    page.goto(live_server.url)
    _make_task_with_notes(page, title="e-from-reader", notes="reader content")

    # Open the reader by clicking 📝 — this does NOT select the task.
    page.locator("#tasks-list .triage-item .notes-icon").first.click()
    expect(page.locator("#notes-read-modal")).to_be_visible()
    # No selected row.
    expect(page.locator("#tasks-list .triage-item.selected")).to_have_count(0)

    page.keyboard.press("e")
    expect(page.locator("#notes-read-modal")).to_be_hidden()
    expect(page.locator("#notes-modal")).to_be_visible()
    expect(page.locator("#notes-modal-input")).to_have_value("reader content")
