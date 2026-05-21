"""End-to-end: focus timer (Tier 2 #9).

Self-contained countdown tool. State machine: idle → launcher → preroll
(3-2-1) → running (MM:SS) → done (Restart / Close). Entry via the topbar
Focus button or `\\f` slash command.

The preroll is real-time (3 seconds), so tests wait through it for the
running-state transition but never wait through a full timer (we test
Cancel instead of expiration).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


HIDDEN = re.compile(r"(^|\s)hidden(\s|$)")


# --- Entry ----------------------------------------------------------------


@pytest.mark.e2e
def test_clicking_focus_button_opens_launcher(page, live_server):
    page.goto(live_server.url)
    expect(page.locator("#focus-launcher")).to_be_hidden()

    page.locator("#focus-btn").click()
    expect(page.locator("#focus-launcher")).to_be_visible()
    # Default duration is 5.
    expect(page.locator("#focus-minutes")).to_have_value("5")
    # Input is focused for immediate typing.
    expect(page.locator("#focus-minutes")).to_be_focused()


@pytest.mark.e2e
def test_backslash_f_opens_launcher(page, live_server):
    page.goto(live_server.url)
    page.keyboard.press("Backslash")
    page.keyboard.press("f")
    expect(page.locator("#focus-launcher")).to_be_visible()


# --- Spinner --------------------------------------------------------------


@pytest.mark.e2e
def test_step_buttons_adjust_by_one(page, live_server):
    page.goto(live_server.url)
    page.locator("#focus-btn").click()

    page.locator("#focus-plus").click()
    expect(page.locator("#focus-minutes")).to_have_value("6")

    page.locator("#focus-minus").click()
    page.locator("#focus-minus").click()
    expect(page.locator("#focus-minutes")).to_have_value("4")


@pytest.mark.e2e
def test_minutes_clamp_to_range(page, live_server):
    """Direct typing then change fires the clamp."""
    page.goto(live_server.url)
    page.locator("#focus-btn").click()

    page.locator("#focus-minutes").fill("99")
    page.locator("#focus-minutes").press("Tab")  # fires change
    expect(page.locator("#focus-minutes")).to_have_value("45")

    page.locator("#focus-minutes").fill("0")
    page.locator("#focus-minutes").press("Tab")
    expect(page.locator("#focus-minutes")).to_have_value("1")


# --- Esc / cancel ---------------------------------------------------------


@pytest.mark.e2e
def test_escape_in_launcher_closes(page, live_server):
    page.goto(live_server.url)
    page.locator("#focus-btn").click()
    expect(page.locator("#focus-launcher")).to_be_visible()

    page.keyboard.press("Escape")
    expect(page.locator("#focus-launcher")).to_be_hidden()


# --- Pre-roll → running ---------------------------------------------------


@pytest.mark.e2e
def test_enter_starts_preroll_then_running(page, live_server):
    page.goto(live_server.url)
    page.locator("#focus-btn").click()
    page.locator("#focus-minutes").fill("2")
    page.locator("#focus-minutes").press("Enter")

    # Launcher closes; overlay shows; preroll state is the visible one.
    expect(page.locator("#focus-launcher")).to_be_hidden()
    expect(page.locator("#focus-overlay")).to_be_visible()
    expect(page.locator("#focus-state-preroll")).not_to_have_class(HIDDEN)
    expect(page.locator("#focus-state-running")).to_have_class(HIDDEN)
    # The preroll number starts at 3.
    expect(page.locator("#focus-preroll-num")).to_have_text("3")

    # Wait ~3.5 s for the preroll to count 3 → 2 → 1 → start.
    page.wait_for_selector(
        "#focus-state-running:not(.hidden)", timeout=4500
    )
    expect(page.locator("#focus-state-preroll")).to_have_class(HIDDEN)
    # MM:SS should be 02:00 (or 01:59 if a tick just passed).
    clock_text = page.locator("#focus-clock").text_content()
    assert clock_text in ("02:00", "01:59"), f"unexpected clock: {clock_text!r}"


@pytest.mark.e2e
def test_cancel_during_running_returns_to_idle(page, live_server):
    page.goto(live_server.url)
    page.locator("#focus-btn").click()
    page.locator("#focus-minutes").fill("2")
    page.locator("#focus-minutes").press("Enter")

    page.wait_for_selector("#focus-state-running:not(.hidden)", timeout=4500)
    page.locator("#focus-cancel-btn").click()

    expect(page.locator("#focus-overlay")).to_be_hidden()
    # Topbar Focus button still works after cancel → state is fully idle.
    page.locator("#focus-btn").click()
    expect(page.locator("#focus-launcher")).to_be_visible()


@pytest.mark.e2e
def test_escape_during_preroll_cancels(page, live_server):
    page.goto(live_server.url)
    page.locator("#focus-btn").click()
    page.locator("#focus-minutes").fill("2")
    page.locator("#focus-minutes").press("Enter")

    # Preroll is visible briefly; cancel via Esc before it elapses.
    expect(page.locator("#focus-overlay")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#focus-overlay")).to_be_hidden()
