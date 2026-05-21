"""Wiring sanity: the server serves the SPA and starts up cleanly under test."""

import pytest


@pytest.mark.unit
def test_root_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    # The page is `index.html` from `web/`. Check for any HTML doctype/tag — we
    # don't pin the exact markup because the page is allowed to evolve.
    body = res.text.lower()
    assert "<!doctype html" in body or "<html" in body


@pytest.mark.unit
def test_isolation_creates_empty_files(client, tmp_data_dir):
    # The lifespan ran inside ``client`` and should have created both stores
    # in the per-test directory — never in the real ``data/`` dir.
    assert (tmp_data_dir / "inbox.json").exists()
    assert (tmp_data_dir / "tasks.json").exists()


@pytest.mark.unit
def test_inbox_and_tasks_start_empty(client):
    inbox = client.get("/api/inbox").json()
    tasks = client.get("/api/tasks").json()
    assert inbox == {"items": []}
    assert tasks == {"items": []}
