"""Tests for the calendar overlay (Phase 7 — read-only .ics overlay).

Synthetic .ics files keep the tests independent of any real calendar data.
The shared ``tmp_data_dir`` fixture already wires ``server.CALENDAR_DIR`` to
``<tmp>/UserCalendar/``; tests create that directory on demand.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# Import paths through the local repo root (conftest manipulates sys.path).
import calendar_overlay


# --- helpers ---------------------------------------------------------------


def _ics(events: str) -> str:
    # The tests pass `events` as an already-indented multiline string (for
    # readability). dedent it first, then drop into the wrapper at a known
    # indent so the *final* outer dedent yields a clean, flush-left .ics.
    body = textwrap.dedent(events).strip()
    return (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//ADHD assistant tests//EN\n"
        f"{body}\n"
        "END:VCALENDAR\n"
    )


def _write_ics(cal_dir: Path, name: str, body: str) -> Path:
    cal_dir.mkdir(parents=True, exist_ok=True)
    p = cal_dir / name
    p.write_text(_ics(body))
    # Bust the module's mtime cache in case a previous test happened to write
    # the same path (tmp_path is unique per test, so this is just defensive).
    calendar_overlay._PARSE_CACHE.pop(p, None)
    return p


@pytest.fixture
def cal_dir(tmp_data_dir):
    return tmp_data_dir / "UserCalendar"


# --- empty / failure modes -------------------------------------------------


@pytest.mark.unit
def test_missing_calendar_dir_returns_empty(tmp_data_dir):
    out = calendar_overlay.events_for_date(
        "2099-06-15", tmp_data_dir / "UserCalendar"
    )
    assert out == []


@pytest.mark.unit
def test_empty_calendar_dir_returns_empty(cal_dir):
    cal_dir.mkdir()
    assert calendar_overlay.events_for_date("2099-06-15", cal_dir) == []


@pytest.mark.unit
def test_non_ics_files_ignored(cal_dir):
    cal_dir.mkdir()
    (cal_dir / "readme.txt").write_text("not a calendar")
    (cal_dir / "notes.json").write_text("{}")
    assert calendar_overlay.events_for_date("2099-06-15", cal_dir) == []


@pytest.mark.unit
def test_parse_error_skips_just_that_file(cal_dir, caplog):
    # One garbage file alongside one valid file. The valid file's events
    # still come back.
    cal_dir.mkdir()
    (cal_dir / "broken.ics").write_text("THIS IS NOT A CALENDAR")
    _write_ics(
        cal_dir,
        "good.ics",
        body="""\
        BEGIN:VEVENT
        UID:good-1
        DTSTART:20990615T140000
        DTEND:20990615T150000
        SUMMARY:Good event
        END:VEVENT
        """,
    )
    out = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert len(out) == 1
    assert out[0]["summary"] == "Good event"


@pytest.mark.unit
def test_bad_date_raises(cal_dir):
    cal_dir.mkdir()
    with pytest.raises(ValueError):
        calendar_overlay.events_for_date("not-a-date", cal_dir)


# --- timed events ----------------------------------------------------------


@pytest.mark.unit
def test_timed_event_on_day(cal_dir):
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:t1
        DTSTART:20990615T140000
        DTEND:20990615T153000
        SUMMARY:Doctor visit
        END:VEVENT
        """,
    )
    [event] = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert event["summary"] == "Doctor visit"
    assert event["allDay"] is False
    assert event["startMin"] == 14 * 60
    assert event["endMin"] == 14 * 60 + 90
    assert event["source"] == "fam"


@pytest.mark.unit
def test_timed_event_on_other_day_excluded(cal_dir):
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:t1
        DTSTART:20990615T140000
        DTEND:20990615T150000
        SUMMARY:Other day
        END:VEVENT
        """,
    )
    assert calendar_overlay.events_for_date("2099-06-14", cal_dir) == []
    assert calendar_overlay.events_for_date("2099-06-16", cal_dir) == []


@pytest.mark.unit
def test_multi_day_timed_event_is_clipped_on_each_day(cal_dir):
    """22:00 day 1 → 02:00 day 2 should appear on both days, clipped to
    each day's window."""
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:span
        DTSTART:20990615T220000
        DTEND:20990616T020000
        SUMMARY:Cross-midnight
        END:VEVENT
        """,
    )
    [d1] = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert d1["startMin"] == 22 * 60
    assert d1["endMin"] == 24 * 60  # clipped at midnight

    [d2] = calendar_overlay.events_for_date("2099-06-16", cal_dir)
    assert d2["startMin"] == 0
    assert d2["endMin"] == 2 * 60


# --- all-day events --------------------------------------------------------


@pytest.mark.unit
def test_all_day_event(cal_dir):
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:vacay
        DTSTART;VALUE=DATE:20990615
        DTEND;VALUE=DATE:20990616
        SUMMARY:Vacation
        END:VEVENT
        """,
    )
    [event] = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert event["summary"] == "Vacation"
    assert event["allDay"] is True
    assert event["startMin"] is None
    assert event["endMin"] is None


@pytest.mark.unit
def test_multi_day_all_day_appears_on_each_spanned_day(cal_dir):
    """An event with DTSTART 2099-06-15 / DTEND 2099-06-18 (exclusive)
    should appear on 15, 16, 17 — but not on 14 or 18."""
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:trip
        DTSTART;VALUE=DATE:20990615
        DTEND;VALUE=DATE:20990618
        SUMMARY:Family trip
        END:VEVENT
        """,
    )
    for d in ("2099-06-15", "2099-06-16", "2099-06-17"):
        out = calendar_overlay.events_for_date(d, cal_dir)
        assert len(out) == 1, f"{d}: expected 1 event, got {out!r}"
        assert out[0]["allDay"] is True

    for d in ("2099-06-14", "2099-06-18"):
        assert calendar_overlay.events_for_date(d, cal_dir) == [], (
            f"{d}: expected no events for a non-spanned day"
        )


# --- recurring events ------------------------------------------------------


@pytest.mark.unit
def test_weekly_recurrence_lands_on_each_week(cal_dir):
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:weekly
        DTSTART:20990615T140000
        DTEND:20990615T150000
        RRULE:FREQ=WEEKLY;COUNT=4
        SUMMARY:Weekly checkin
        END:VEVENT
        """,
    )
    # The four occurrences: Jun 15, Jun 22, Jun 29, Jul 6.
    for d in ("2099-06-15", "2099-06-22", "2099-06-29", "2099-07-06"):
        out = calendar_overlay.events_for_date(d, cal_dir)
        assert len(out) == 1, f"{d}: expected one occurrence"
        assert out[0]["summary"] == "Weekly checkin"
        assert out[0]["startMin"] == 14 * 60

    # A non-occurrence date.
    assert calendar_overlay.events_for_date("2099-06-16", cal_dir) == []
    # After COUNT=4 expires.
    assert calendar_overlay.events_for_date("2099-07-13", cal_dir) == []


# --- multiple sources + sorting -------------------------------------------


@pytest.mark.unit
def test_sort_all_day_first_then_by_start(cal_dir):
    # Two timed + one all-day. Output order should be: all-day, then 09:00,
    # then 14:00.
    _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:e1
        DTSTART:20990615T140000
        DTEND:20990615T150000
        SUMMARY:Afternoon
        END:VEVENT
        BEGIN:VEVENT
        UID:e2
        DTSTART:20990615T090000
        DTEND:20990615T100000
        SUMMARY:Morning
        END:VEVENT
        BEGIN:VEVENT
        UID:e3
        DTSTART;VALUE=DATE:20990615
        DTEND;VALUE=DATE:20990616
        SUMMARY:Holiday
        END:VEVENT
        """,
    )
    out = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert [e["summary"] for e in out] == ["Holiday", "Morning", "Afternoon"]


# --- mtime-based cache -----------------------------------------------------


@pytest.mark.unit
def test_mtime_change_busts_the_cache(cal_dir):
    """Re-writing the file should re-parse on the next call. We force a
    different mtime by sleeping past the filesystem's resolution and
    re-touching."""
    import os
    import time as _time

    p = _write_ics(
        cal_dir,
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:before
        DTSTART:20990615T090000
        DTEND:20990615T100000
        SUMMARY:Before
        END:VEVENT
        """,
    )
    first = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert [e["summary"] for e in first] == ["Before"]

    # Overwrite with different content and bump mtime by a full second so
    # filesystems with low resolution still see a difference.
    p.write_text(
        _ics(
            """\
            BEGIN:VEVENT
            UID:after
            DTSTART:20990615T100000
            DTEND:20990615T110000
            SUMMARY:After
            END:VEVENT
            """
        )
    )
    later = _time.time() + 1
    os.utime(p, (later, later))

    second = calendar_overlay.events_for_date("2099-06-15", cal_dir)
    assert [e["summary"] for e in second] == ["After"]


# --- HTTP endpoint ---------------------------------------------------------


@pytest.mark.unit
def test_endpoint_returns_events_for_date(client, tmp_data_dir):
    _write_ics(
        tmp_data_dir / "UserCalendar",
        "fam.ics",
        body="""\
        BEGIN:VEVENT
        UID:e1
        DTSTART:20990615T140000
        DTEND:20990615T150000
        SUMMARY:Doctor
        END:VEVENT
        """,
    )
    res = client.get("/api/calendar/events?date=2099-06-15")
    assert res.status_code == 200
    data = res.json()
    assert data["events"][0]["summary"] == "Doctor"


@pytest.mark.unit
def test_endpoint_empty_when_no_directory(client):
    res = client.get("/api/calendar/events?date=2099-06-15")
    assert res.status_code == 200
    assert res.json() == {"events": []}


@pytest.mark.unit
def test_endpoint_bad_date_rejected(client):
    res = client.get("/api/calendar/events?date=not-a-date")
    assert res.status_code == 400


@pytest.mark.unit
def test_endpoint_missing_date_param_rejected(client):
    res = client.get("/api/calendar/events")
    assert res.status_code == 422  # FastAPI's automatic query-param validation
