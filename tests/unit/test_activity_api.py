"""Unit tests: the activity log API powering the momentum gauge.

`POST /api/activity` bumps the per-(server-local-)day count; `GET /api/activity`
returns the {date: count} map. The log lives in its own `activity.json`, not the
versioned task/inbox schema chain.
"""

from __future__ import annotations

import datetime as dt
import json


def test_ensure_data_creates_activity_file(client, tmp_data_dir):
    # The lifespan (entered by the client fixture) ran ensure_data().
    path = tmp_data_dir / "activity.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data == {"version": 1, "days": {}}


def test_get_activity_starts_empty(client):
    res = client.get("/api/activity")
    assert res.status_code == 200
    assert res.json() == {"days": {}}


def test_post_activity_bumps_today(client):
    today = dt.date.today().isoformat()

    res = client.post("/api/activity")
    assert res.status_code == 200
    body = res.json()
    assert body["date"] == today
    assert body["count"] == 1

    # A second ping increments to 2.
    res2 = client.post("/api/activity")
    assert res2.json()["count"] == 2

    # GET reflects the accumulated count for today.
    got = client.get("/api/activity").json()
    assert got["days"].get(today) == 2


def test_post_activity_persists_to_disk(client, tmp_data_dir):
    client.post("/api/activity")
    client.post("/api/activity")
    client.post("/api/activity")
    on_disk = json.loads((tmp_data_dir / "activity.json").read_text())
    assert on_disk["version"] == 1
    assert on_disk["days"][dt.date.today().isoformat()] == 3


def test_get_activity_tolerates_extra_days(client, tmp_data_dir):
    # Pre-seed a prior day; the API should return it alongside today.
    path = tmp_data_dir / "activity.json"
    path.write_text(json.dumps({"version": 1, "days": {"2099-01-02": 4}}))
    got = client.get("/api/activity").json()
    assert got["days"]["2099-01-02"] == 4
