"""Tests for ``server.migrate_days``.

The migration runs once on startup, folding legacy per-day JSON files into the
single ``tasks.json`` store. Each test exercises one shape of input and asserts
on both the resulting store contents and the on-disk file state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import server


# --- helpers ---------------------------------------------------------------


FIXED_NOW = 1_700_000_000.0


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_tasks_file(path: Path, items: list[dict] | None = None) -> None:
    write_json(path, {"items": items or []})


def make_day_file(days_dir: Path, date_str: str, tasks: list[dict]) -> Path:
    p = days_dir / f"{date_str}.json"
    write_json(p, {"tasks": tasks})
    return p


@pytest.fixture
def migration_paths(tmp_path):
    """Provide the two paths the migration takes as arguments."""
    days_dir = tmp_path / "days"
    days_dir.mkdir()
    tasks_file = tmp_path / "tasks.json"
    make_tasks_file(tasks_file)
    return days_dir, tasks_file


# --- tests -----------------------------------------------------------------


@pytest.mark.unit
def test_empty_days_dir_is_noop(migration_paths):
    days_dir, tasks_file = migration_paths
    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)
    assert summary == {"renamed": 0, "added": 0, "updated": 0}
    assert read_json(tasks_file) == {"items": []}


@pytest.mark.unit
def test_missing_days_dir_is_noop(tmp_path):
    days_dir = tmp_path / "nope"  # never created
    tasks_file = tmp_path / "tasks.json"
    make_tasks_file(tasks_file, [{"id": "keep", "title": "x", "createdAt": 1.0}])
    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)
    assert summary == {"renamed": 0, "added": 0, "updated": 0}
    assert read_json(tasks_file)["items"] == [
        {"id": "keep", "title": "x", "createdAt": 1.0}
    ]


@pytest.mark.unit
def test_new_task_is_added_with_schedule(migration_paths):
    days_dir, tasks_file = migration_paths
    make_day_file(
        days_dir,
        "2026-05-19",
        [
            {
                "id": "abc123",
                "title": "Work SNOW cases",
                "startMin": 600,
                "durationMin": 90,
                "done": False,
                "notes": None,
            }
        ],
    )

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    assert summary == {"renamed": 1, "added": 1, "updated": 0}
    items = read_json(tasks_file)["items"]
    assert len(items) == 1
    task = items[0]
    assert task["id"] == "abc123"
    assert task["title"] == "Work SNOW cases"
    # Tier 2 #12: migrate_days no longer writes the legacy status field.
    assert "status" not in task
    assert task["notes"] is None
    assert task["done"] is False
    assert task["createdAt"] == FIXED_NOW
    assert task["schedule"] == {
        "date": "2026-05-19",
        "startMin": 600,
        "durationMin": 90,
    }

    # Source file renamed.
    assert not (days_dir / "2026-05-19.json").exists()
    assert (days_dir / "2026-05-19.json.migrated").exists()


@pytest.mark.unit
def test_existing_task_gets_schedule_filled_in(migration_paths):
    days_dir, tasks_file = migration_paths
    # Existing task in tasks.json without a schedule.
    make_tasks_file(
        tasks_file,
        [
            {
                "id": "abc123",
                "title": "Pre-existing",
                "status": "active",
                "notes": None,
                "createdAt": 1.0,
            }
        ],
    )
    make_day_file(
        days_dir,
        "2026-05-19",
        [
            {
                "id": "abc123",
                "title": "Day-file title (should be ignored)",
                "startMin": 540,
                "durationMin": 30,
                "done": True,
                "notes": "stuff",
            }
        ],
    )

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    assert summary == {"renamed": 1, "added": 0, "updated": 1}
    task = read_json(tasks_file)["items"][0]
    # Title is preserved from the existing record (we trust tasks.json).
    assert task["title"] == "Pre-existing"
    # Schedule is filled in from the day file.
    assert task["schedule"] == {
        "date": "2026-05-19",
        "startMin": 540,
        "durationMin": 30,
    }
    # Notes were empty → filled from day file.
    assert task["notes"] == "stuff"
    # done was missing → set from day file.
    assert task["done"] is True
    # createdAt preserved.
    assert task["createdAt"] == 1.0


@pytest.mark.unit
def test_second_run_is_a_noop(migration_paths):
    days_dir, tasks_file = migration_paths
    make_day_file(
        days_dir,
        "2026-05-19",
        [{"id": "abc123", "title": "x", "startMin": 600, "durationMin": 90}],
    )

    first = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)
    assert first["renamed"] == 1

    snapshot = read_json(tasks_file)
    second = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW + 100)
    assert second == {"renamed": 0, "added": 0, "updated": 0}
    # tasks.json untouched.
    assert read_json(tasks_file) == snapshot


@pytest.mark.unit
def test_already_migrated_files_are_skipped(migration_paths):
    days_dir, tasks_file = migration_paths
    # Pre-rename a file as if a previous run already processed it.
    write_json(
        days_dir / "2026-05-18.json.migrated",
        {"tasks": [{"id": "stale", "title": "old"}]},
    )

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    assert summary == {"renamed": 0, "added": 0, "updated": 0}
    assert read_json(tasks_file) == {"items": []}


@pytest.mark.unit
def test_non_json_files_are_ignored(migration_paths):
    days_dir, tasks_file = migration_paths
    (days_dir / "README.txt").write_text("notes about migration")
    (days_dir / "garbage").write_text("nothing")
    make_day_file(
        days_dir, "2026-05-19", [{"id": "a", "startMin": 0, "durationMin": 30}]
    )

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    assert summary["renamed"] == 1
    assert summary["added"] == 1
    # Non-json files untouched.
    assert (days_dir / "README.txt").exists()
    assert (days_dir / "garbage").exists()


@pytest.mark.unit
def test_bad_date_stem_is_skipped(migration_paths):
    days_dir, tasks_file = migration_paths
    write_json(days_dir / "not-a-date.json", {"tasks": [{"id": "x"}]})

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    assert summary == {"renamed": 0, "added": 0, "updated": 0}
    # File left alone.
    assert (days_dir / "not-a-date.json").exists()
    assert read_json(tasks_file) == {"items": []}


@pytest.mark.unit
def test_corrupt_json_is_skipped_gracefully(migration_paths):
    days_dir, tasks_file = migration_paths
    (days_dir / "2026-05-19.json").write_text("{not valid json")
    make_day_file(
        days_dir, "2026-05-20", [{"id": "y", "startMin": 0, "durationMin": 30}]
    )

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    # The good file was processed; the corrupt one was skipped without
    # blocking the run.
    assert summary["added"] == 1
    assert (days_dir / "2026-05-20.json.migrated").exists()
    # Corrupt file is still there, unrenamed.
    assert (days_dir / "2026-05-19.json").exists()
    assert not (days_dir / "2026-05-19.json.migrated").exists()


@pytest.mark.unit
def test_task_without_id_is_skipped(migration_paths):
    days_dir, tasks_file = migration_paths
    make_day_file(
        days_dir,
        "2026-05-19",
        [
            {"title": "no id", "startMin": 0, "durationMin": 30},
            {"id": "real", "startMin": 60, "durationMin": 30},
        ],
    )

    summary = server.migrate_days(days_dir, tasks_file, now=FIXED_NOW)

    assert summary == {"renamed": 1, "added": 1, "updated": 0}
    ids = [t["id"] for t in read_json(tasks_file)["items"]]
    assert ids == ["real"]
