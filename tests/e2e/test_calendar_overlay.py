"""End-to-end: calendar overlay (Phase 7 — read-only `.ics`).

Seeds a small synthetic `.ics` into the test's isolated `ADHD_DATA_DIR/
UserCalendar/`, then navigates to the matching date and verifies:
  - Timed events render as dimmed `.calendar-event` blocks inside `#tracks`
  - All-day events show up as `.all-day-chip` in the `#all-day-strip`
  - Changing the date refreshes the overlay
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect


def _write_seed_ics(data_dir: Path) -> None:
    """A synthetic calendar covering one timed event + one all-day event on
    2099-06-15, plus a weekly-recurring event so we have something on the
    16th too for the date-navigation case."""
    cal_dir = data_dir / "UserCalendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    (cal_dir / "fam.ics").write_text(
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//ADHD assistant E2E//EN\n"
        "BEGIN:VEVENT\n"
        "UID:timed-1\n"
        "DTSTART:20990615T140000\n"
        "DTEND:20990615T153000\n"
        "SUMMARY:Doctor visit\n"
        "END:VEVENT\n"
        "BEGIN:VEVENT\n"
        "UID:allday-1\n"
        "DTSTART;VALUE=DATE:20990615\n"
        "DTEND;VALUE=DATE:20990616\n"
        "SUMMARY:Vacation\n"
        "END:VEVENT\n"
        "BEGIN:VEVENT\n"
        "UID:recurring-1\n"
        "DTSTART:20990616T090000\n"
        "DTEND:20990616T093000\n"
        "RRULE:FREQ=DAILY;COUNT=3\n"
        "SUMMARY:Standup\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )


def _jump_to(page, date: str) -> None:
    page.locator("#date-picker").evaluate(
        f"el => {{ el.value = '{date}'; el.dispatchEvent(new Event('change')); }}"
    )


@pytest.mark.e2e
def test_timed_event_renders_as_calendar_event_block(page, live_server):
    _write_seed_ics(live_server.data_dir)
    page.goto(live_server.url)
    _jump_to(page, "2099-06-15")

    block = page.locator("#tracks .calendar-event").filter(
        has_text="Doctor visit"
    )
    expect(block).to_be_visible()
    # 14:00 = 840 min from midnight → top: 840px (1 px/min).
    top_px = float(
        page.evaluate(
            "(el) => el.style.top.replace('px', '')",
            block.element_handle(),
        )
    )
    assert top_px == pytest.approx(840, abs=1)


@pytest.mark.e2e
def test_calendar_block_is_non_interactive(page, live_server):
    """Calendar events must not steal clicks from real task blocks beneath.
    `pointer-events: none` should resolve via computed style."""
    _write_seed_ics(live_server.data_dir)
    page.goto(live_server.url)
    _jump_to(page, "2099-06-15")

    block = page.locator("#tracks .calendar-event").first
    expect(block).to_be_visible()
    pe = page.evaluate(
        "(el) => getComputedStyle(el).pointerEvents",
        block.element_handle(),
    )
    assert pe == "none"


@pytest.mark.e2e
def test_all_day_event_appears_in_pinned_strip(page, live_server):
    _write_seed_ics(live_server.data_dir)
    page.goto(live_server.url)
    _jump_to(page, "2099-06-15")

    chip = page.locator("#all-day-strip .all-day-chip").filter(
        has_text="Vacation"
    )
    expect(chip).to_be_visible()
    # Strip must sit *outside* the scroll container so it stays pinned.
    same_parent = page.evaluate(
        """() => {
            const strip = document.querySelector('#all-day-strip');
            const timeline = document.querySelector('#timeline');
            return strip && timeline && !timeline.contains(strip);
        }"""
    )
    assert same_parent, "all-day-strip must not live inside the timeline scroller"


@pytest.mark.e2e
def test_date_navigation_refreshes_overlay(page, live_server):
    """Step forward one day with the › arrow — yesterday's Doctor visit
    should disappear and today's Standup should appear."""
    _write_seed_ics(live_server.data_dir)
    page.goto(live_server.url)
    _jump_to(page, "2099-06-15")

    expect(
        page.locator(".calendar-event").filter(has_text="Doctor visit")
    ).to_be_visible()
    # Sanity: no Standup on the 15th.
    expect(
        page.locator(".calendar-event").filter(has_text="Standup")
    ).to_have_count(0)

    page.locator("#date-next").click()
    # 16th now showing — Doctor visit gone, Standup present.
    expect(
        page.locator(".calendar-event").filter(has_text="Doctor visit")
    ).to_have_count(0)
    expect(
        page.locator(".calendar-event").filter(has_text="Standup")
    ).to_be_visible()


@pytest.mark.e2e
def test_no_calendar_dir_means_empty_overlay(page, live_server):
    """When no UserCalendar/ exists, the overlay stays empty without error."""
    page.goto(live_server.url)
    _jump_to(page, "2099-06-15")
    expect(page.locator(".calendar-event")).to_have_count(0)
    expect(page.locator(".all-day-chip")).to_have_count(0)
