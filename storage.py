"""Persistence primitives for the ADHD assistant.

This module owns *how* data goes to disk; ``server.py`` owns *what* shape it
has and *which* HTTP routes touch it. Splitting them keeps the file sizes
manageable and lets storage primitives be reused outside the request cycle
(migration scripts, tests, future CLI).

Imported names re-exposed on ``server``:

  * Path constants: ``DATA``, ``DAYS_DIR``, ``INBOX_FILE``, ``TASKS_FILE``
  * Atomic IO: ``read_json``, ``write_json``
  * IDs: ``new_id``
  * Schema versioning: ``CURRENT_VERSION``, ``load_versioned``, ``save_versioned``
  * One-shot day-files → tasks.json fold: ``migrate_days``

The path constants are evaluated once at import time. Tests that need
isolation should monkeypatch the names on the ``server`` module so route
handlers (which read those names from ``server``'s globals) see the override.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
# Allow tests to point at an isolated data directory via an env var; production
# / dev runs unchanged.
_env_data = os.environ.get("ADHD_DATA_DIR")
DATA = Path(_env_data) if _env_data else ROOT / "data"
DAYS_DIR = DATA / "days"
INBOX_FILE = DATA / "inbox.json"
TASKS_FILE = DATA / "tasks.json"
CALENDAR_DIR = DATA / "UserCalendar"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- Atomic IO --------------------------------------------------------------


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict) -> None:
    # Atomic write: temp file in same dir, then os.replace.
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def new_id() -> str:
    return secrets.token_urlsafe(8)


# --- Schema versioning ------------------------------------------------------
# Bump CURRENT_VERSION when changing the on-disk shape and register an upgrade
# function in _UPGRADES. load_versioned() chains upgrades on read and persists
# the result so old files become current-shaped after a single read.

CURRENT_VERSION = 2


def _upgrade_v0_to_v1(data: dict) -> dict:
    """Stamp the version marker on pre-A3 files.

    The on-disk shape was already ``{"items": [...]}`` so this is a no-op
    apart from adding ``version: 1``.
    """
    data["version"] = 1
    return data


def _upgrade_v1_to_v2(data: dict) -> dict:
    """Drop the ``status: active | not_today`` field.

    P5#12 replaced the Now/Later toggle with a snooze mechanism. The
    ``status`` field becomes meaningless: items that were ``not_today``
    resurface to the main list (the user can re-snooze them properly).
    New fields ``snoozedUntil``, ``recurring``, ``dueDate`` get backfilled
    lazily by ``_normalize_task`` on read; we don't bother writing them
    here.
    """
    for item in data.get("items", []):
        item.pop("status", None)
    data["version"] = 2
    return data


_UPGRADES = {0: _upgrade_v0_to_v1, 1: _upgrade_v1_to_v2}


def load_versioned(path: Path) -> dict:
    """Read a JSON file, run any pending schema upgrades, persist if upgraded.

    Raises ``RuntimeError`` if the file's version is newer than this server
    understands, so an accidentally-downgraded server doesn't silently chew
    on data it can't interpret.
    """
    raw = read_json(path)
    version = raw.get("version", 0)
    if version > CURRENT_VERSION:
        raise RuntimeError(
            f"{path.name} is at schema version {version}; "
            f"this server supports up to {CURRENT_VERSION}"
        )
    upgraded = False
    while version < CURRENT_VERSION:
        upgrade = _UPGRADES.get(version)
        if upgrade is None:
            raise RuntimeError(
                f"no upgrade path registered from version {version}"
            )
        raw = upgrade(raw)
        new_version = raw.get("version", version + 1)
        if new_version <= version:
            raise RuntimeError(
                f"upgrade from {version} did not advance the version"
            )
        version = new_version
        upgraded = True
    if upgraded:
        write_json(path, raw)
    return raw


def save_versioned(path: Path, payload: dict) -> None:
    """Write a JSON file, stamping ``version`` to ``CURRENT_VERSION``."""
    out = dict(payload)
    out["version"] = CURRENT_VERSION
    write_json(path, out)


# --- One-shot day-files → tasks.json fold ----------------------------------


def migrate_days(days_dir: Path, tasks_file: Path, *, now: float) -> dict:
    """Fold any tasks from per-day JSON files into ``tasks_file``.

    All paths and the wall-clock are passed in so the function is unit-testable
    without booting the server.

    Behavior:
      - Each ``YYYY-MM-DD.json`` file in ``days_dir`` is read once.
      - Tasks not yet in ``tasks_file`` are added with their ``schedule``
        populated from the filename's date and the per-task ``startMin`` /
        ``durationMin``. New records use ``now`` as ``createdAt``.
      - Tasks already in ``tasks_file`` (matched by ``id``) have their
        ``schedule`` filled in when absent; ``notes`` are filled when the
        existing record's notes are empty; ``done`` is filled when missing.
      - On success each source file is renamed to ``<name>.json.migrated`` so
        repeated invocations are idempotent.
      - Files whose stem doesn't match ``YYYY-MM-DD``, or which fail to parse,
        are skipped silently.

    Returns a summary ``{"renamed": int, "added": int, "updated": int}``.
    """
    summary = {"renamed": 0, "added": 0, "updated": 0}
    if not days_dir.exists():
        return summary

    tasks_data = read_json(tasks_file)
    items = tasks_data.setdefault("items", [])
    by_id = {it["id"]: it for it in items}
    dirty = False

    for path in sorted(days_dir.iterdir()):
        if not path.is_file() or path.suffix != ".json":
            continue
        date_str = path.stem
        if not DATE_RE.match(date_str):
            continue
        try:
            day_data = read_json(path)
        except Exception:
            continue

        for t in day_data.get("tasks", []):
            tid = t.get("id")
            if not tid:
                continue
            schedule = {
                "date": date_str,
                "startMin": int(t.get("startMin", 0)),
                "durationMin": int(t.get("durationMin", 30)),
            }
            existing = by_id.get(tid)
            if existing is None:
                rec = {
                    "id": tid,
                    "title": t.get("title", "(untitled)"),
                    "notes": t.get("notes"),
                    "schedule": schedule,
                    "done": bool(t.get("done", False)),
                    "tags": [],
                    "defaultDurationMin": schedule["durationMin"],
                    "dueDate": None,
                    "recurring": False,
                    "snoozedUntil": None,
                    "createdAt": now,
                    "updatedAt": now,
                    "completedAt": None,
                }
                items.append(rec)
                by_id[tid] = rec
                summary["added"] += 1
                dirty = True
            else:
                touched = False
                if not existing.get("schedule"):
                    existing["schedule"] = schedule
                    touched = True
                if existing.get("notes") in (None, "") and t.get("notes"):
                    existing["notes"] = t["notes"]
                    touched = True
                if "done" not in existing:
                    existing["done"] = bool(t.get("done", False))
                    touched = True
                if touched:
                    summary["updated"] += 1
                    dirty = True

        path.rename(path.with_suffix(".json.migrated"))
        summary["renamed"] += 1

    if dirty:
        write_json(tasks_file, tasks_data)
    return summary
