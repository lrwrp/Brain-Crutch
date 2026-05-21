"""Read-only calendar overlay.

Parses ``data/UserCalendar/*.ics`` files and returns events overlapping a
requested local-date day. Strictly one-way: the tracker never writes back to
the user's calendar.

Module is named ``calendar_overlay`` rather than ``calendar`` so it doesn't
shadow the stdlib ``calendar`` module that ``icalendar`` itself imports
internally.

Caching:
  Per source file, keyed by ``(path, mtime)``. The first call to
  ``events_for_date`` after a file changes re-parses; subsequent calls reuse
  the cached ``Calendar`` object. Cheap and survives the lifetime of the
  uvicorn process.

Failure modes:
  * Missing source directory → ``[]`` (no events).
  * Empty directory → ``[]``.
  * Per-file parse error → logged once, that file skipped, others still
    served. Never raises out to the caller.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from pathlib import Path
from typing import Dict, List

import recurring_ical_events
from icalendar import Calendar

log = logging.getLogger("calendar_overlay")

# YYYY-MM-DD validation lives in storage.DATE_RE but importing it here would
# create an unnecessary coupling; re-declare locally.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Cache: {path: (mtime, Calendar)}. Module-global so a fresh request reuses
# parsed calendars without re-reading from disk.
_PARSE_CACHE: Dict[Path, "tuple[float, Calendar]"] = {}


def _local_midnight(date_str: str) -> _dt.datetime:
    """Return tz-aware local midnight for the given YYYY-MM-DD date."""
    y, m, d = (int(x) for x in date_str.split("-"))
    # System local tz; matches how task ``schedule.startMin`` is interpreted.
    return _dt.datetime(y, m, d, 0, 0, 0).astimezone()


def _load_calendar(path: Path) -> Calendar | None:
    """Return the parsed Calendar for ``path``, using the mtime cache."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        # File disappeared between listdir and stat — drop from cache and
        # return None so the caller skips it cleanly.
        _PARSE_CACHE.pop(path, None)
        return None

    cached = _PARSE_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with path.open("rb") as f:
            cal = Calendar.from_ical(f.read())
    except Exception as e:  # noqa: BLE001 — robustness > specificity for parse
        log.warning("Failed to parse %s: %s", path.name, e)
        return None
    _PARSE_CACHE[path] = (mtime, cal)
    return cal


def _minute_of_local_day(dt: _dt.datetime, day_start: _dt.datetime) -> int:
    """Project ``dt`` onto the local-day timeline (minutes since midnight)."""
    delta = dt.astimezone(day_start.tzinfo) - day_start
    return int(delta.total_seconds() // 60)


def _event_to_dict(event, day_start: _dt.datetime, source: str) -> dict | None:
    """Convert an expanded VEVENT to the response shape, clipped to the day.

    Returns ``None`` for events that don't actually overlap the day (recurring
    expanders are sometimes generous about boundary cases).
    """
    summary = str(event.get("SUMMARY", "")).strip() or "(untitled event)"
    dtstart = event["DTSTART"].dt
    dtend = event["DTEND"].dt if "DTEND" in event else dtstart

    day_end = day_start + _dt.timedelta(days=1)

    # All-day events use ``date`` (not ``datetime``). DTEND on all-day events
    # is exclusive per RFC 5545.
    if isinstance(dtstart, _dt.date) and not isinstance(dtstart, _dt.datetime):
        start_date = dtstart
        end_date = dtend if isinstance(dtend, _dt.date) and not isinstance(
            dtend, _dt.datetime
        ) else dtstart + _dt.timedelta(days=1)
        if end_date <= day_start.date() or start_date >= day_end.date():
            return None
        return {
            "summary": summary,
            "allDay": True,
            "startMin": None,
            "endMin": None,
            "source": source,
        }

    # Timed event. Ensure tz-aware.
    if dtstart.tzinfo is None:
        dtstart = dtstart.replace(tzinfo=day_start.tzinfo)
    if dtend.tzinfo is None:
        dtend = dtend.replace(tzinfo=day_start.tzinfo)

    # Clip to the requested day's window.
    clipped_start = max(dtstart, day_start)
    clipped_end = min(dtend, day_end)
    if clipped_end <= clipped_start:
        return None

    start_min = _minute_of_local_day(clipped_start, day_start)
    end_min = _minute_of_local_day(clipped_end, day_start)
    # Defensive clamp — expander rounding shouldn't put us outside [0, 1440],
    # but better to be safe than render a block off-canvas.
    start_min = max(0, min(1440, start_min))
    end_min = max(0, min(1440, end_min))
    if end_min <= start_min:
        return None
    return {
        "summary": summary,
        "allDay": False,
        "startMin": start_min,
        "endMin": end_min,
        "source": source,
    }


def events_for_date(date_str: str, calendar_dir: Path) -> List[dict]:
    """All calendar events overlapping the requested local-date day.

    ``date_str`` must be a YYYY-MM-DD string; otherwise a ``ValueError`` is
    raised. ``calendar_dir`` is the directory to scan for ``*.ics``; non-
    existent or empty → ``[]``.

    Output is a flat list. Multi-day timed events are clipped to the day's
    window; multi-day all-day events appear on each day they span. The list
    is sorted: all-day first (alphabetical by summary), then timed by
    ``startMin``.
    """
    if not _DATE_RE.match(date_str):
        raise ValueError(f"bad date: {date_str!r}")
    if not calendar_dir.exists() or not calendar_dir.is_dir():
        return []

    day_start = _local_midnight(date_str)
    day_end = day_start + _dt.timedelta(days=1)

    out: List[dict] = []
    for path in sorted(calendar_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".ics":
            continue
        cal = _load_calendar(path)
        if cal is None:
            continue
        source = path.stem
        try:
            expanded = recurring_ical_events.of(cal).between(day_start, day_end)
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to expand recurrences in %s: %s", path.name, e)
            continue
        for ev in expanded:
            entry = _event_to_dict(ev, day_start, source)
            if entry is not None:
                out.append(entry)

    out.sort(
        key=lambda e: (
            0 if e["allDay"] else 1,
            e.get("startMin") or 0,
            e["summary"],
        )
    )
    return out
