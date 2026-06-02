"""Shared fixtures for the ADHD assistant test suite.

Every test gets an isolated data directory via ``tmp_data_dir`` so no test ever
touches real user data. The ``client`` fixture wraps the FastAPI app with a
``TestClient`` whose lifespan runs against the isolated paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Point ``server`` at a fresh data directory under ``tmp_path``.

    The four module-level path constants in ``server`` are reassigned via
    ``monkeypatch.setattr`` so the lifespan, route handlers, and ``write_json``
    all read and write within ``tmp_path``.
    """
    import server

    data = tmp_path / "data"
    days = data / "days"
    data.mkdir()
    days.mkdir()

    monkeypatch.setattr(server, "DATA", data)
    monkeypatch.setattr(server, "DAYS_DIR", days)
    monkeypatch.setattr(server, "INBOX_FILE", data / "inbox.json")
    monkeypatch.setattr(server, "TASKS_FILE", data / "tasks.json")
    monkeypatch.setattr(server, "ACTIVITY_FILE", data / "activity.json")
    monkeypatch.setattr(server, "CALENDAR_DIR", data / "UserCalendar")
    return data


@pytest.fixture
def client(tmp_data_dir):
    """A ``TestClient`` bound to the isolated data directory.

    Entering the context manager triggers the FastAPI lifespan, which calls
    ``ensure_data()`` against the patched paths and creates empty
    ``inbox.json`` and ``tasks.json``.
    """
    import server

    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def make_task(client):
    """Factory: POST a task and return its dict.

    Usage: ``task = make_task(title="Read docs", priority="high")``.
    """

    def _make(**overrides):
        body = {"title": "Untitled"}
        body.update(overrides)
        res = client.post("/api/tasks", json=body)
        assert res.status_code == 200, res.text
        return res.json()

    return _make


@pytest.fixture
def make_inbox(client):
    """Factory: POST an inbox item and return its dict."""

    def _make(text="something captured"):
        res = client.post("/api/inbox", json={"text": text})
        assert res.status_code == 200, res.text
        return res.json()

    return _make
