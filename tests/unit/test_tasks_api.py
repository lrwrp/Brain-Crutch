"""Tests for the tasks HTTP API.

Covers POST/PATCH/DELETE/GET ``/api/tasks`` and the derived ``/api/day/{date}``
view. Each ``client`` fixture spin-up starts from an empty store.
"""

from __future__ import annotations

import pytest


# --- POST /api/tasks --------------------------------------------------------


@pytest.mark.unit
class TestCreateTask:
    def test_minimal_payload_uses_defaults(self, client):
        res = client.post("/api/tasks", json={"title": "Read book"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["title"] == "Read book"
        assert data["priority"] == "medium"
        assert data["notes"] is None
        assert data["schedule"] is None
        assert data["done"] is False
        # Tier 2 #12: new fields default to null/false.
        assert data["dueDate"] is None
        assert data["recurring"] is False
        assert data["snoozedUntil"] is None
        # Legacy status field is gone.
        assert "status" not in data
        assert isinstance(data["id"], str) and data["id"]
        assert isinstance(data["createdAt"], float)

    def test_full_payload_round_trips(self, client):
        body = {
            "title": "Big task",
            "priority": "high",
            "notes": "important context",
            "schedule": {"date": "2026-05-20", "startMin": 540, "durationMin": 60},
            "done": False,
        }
        data = client.post("/api/tasks", json=body).json()
        assert data["title"] == "Big task"
        assert data["priority"] == "high"
        assert data["notes"] == "important context"
        assert data["schedule"] == body["schedule"]

    def test_title_is_stripped(self, client):
        data = client.post("/api/tasks", json={"title": "  trimmed  "}).json()
        assert data["title"] == "trimmed"

    def test_notes_are_stripped(self, client):
        data = client.post(
            "/api/tasks", json={"title": "x", "notes": "  hello  "}
        ).json()
        assert data["notes"] == "hello"

    def test_empty_title_rejected(self, client):
        res = client.post("/api/tasks", json={"title": ""})
        assert res.status_code == 400

    def test_whitespace_title_rejected(self, client):
        res = client.post("/api/tasks", json={"title": "   "})
        assert res.status_code == 400

    def test_legacy_status_field_silently_ignored(self, client):
        """Tier 2 #12 dropped the active/not_today status. POSTs with the
        legacy field are accepted (extra=ignore on Pydantic) and the
        response carries no status key."""
        res = client.post(
            "/api/tasks", json={"title": "x", "status": "not_today"}
        )
        assert res.status_code == 200
        assert "status" not in res.json()

    def test_unknown_priority_rejected(self, client):
        res = client.post("/api/tasks", json={"title": "x", "priority": "urgent"})
        assert res.status_code == 400

    def test_bad_schedule_date_rejected(self, client):
        res = client.post(
            "/api/tasks",
            json={
                "title": "x",
                "schedule": {"date": "not-a-date", "startMin": 0, "durationMin": 30},
            },
        )
        # Pydantic field_validator → 422 unprocessable entity.
        assert res.status_code == 422

    def test_out_of_range_start_min_rejected(self, client):
        res = client.post(
            "/api/tasks",
            json={
                "title": "x",
                "schedule": {"date": "2026-05-20", "startMin": -1, "durationMin": 30},
            },
        )
        assert res.status_code == 422

    def test_zero_duration_rejected(self, client):
        res = client.post(
            "/api/tasks",
            json={
                "title": "x",
                "schedule": {"date": "2026-05-20", "startMin": 0, "durationMin": 0},
            },
        )
        assert res.status_code == 422

    def test_client_supplied_id_is_ignored_server_mints_its_own(self, client):
        """A4: IDs are server-only. A client that smuggles an ``id`` field
        must not be able to pin the row to a chosen value — the server
        ignores it and mints a fresh id."""
        spoofed = "client-spoofed-id"
        data = client.post(
            "/api/tasks", json={"title": "honest", "id": spoofed}
        ).json()
        assert data["id"] != spoofed
        # And no row exists with the spoofed id either.
        items = client.get("/api/tasks").json()["items"]
        assert all(it["id"] != spoofed for it in items)


# --- PATCH /api/tasks/{id} --------------------------------------------------


@pytest.mark.unit
class TestPatchTask:
    def test_rename(self, client, make_task):
        t = make_task(title="Old")
        res = client.patch(f"/api/tasks/{t['id']}", json={"title": "New"})
        assert res.status_code == 200
        assert res.json()["title"] == "New"

    def test_rename_to_whitespace_rejected_and_preserves_title(self, client, make_task):
        t = make_task(title="Old")
        res = client.patch(f"/api/tasks/{t['id']}", json={"title": "   "})
        assert res.status_code == 400
        # Title preserved on rejection.
        items = client.get("/api/tasks").json()["items"]
        assert items[0]["title"] == "Old"

    def test_legacy_status_in_patch_silently_ignored(self, client, make_task):
        """Tier 2 #12 dropped status. A PATCH carrying the legacy field is
        accepted as a no-op (Pydantic ignores unknown fields)."""
        t = make_task()
        res = client.patch(
            f"/api/tasks/{t['id']}", json={"status": "not_today"}
        )
        assert res.status_code == 200
        assert "status" not in res.json()

    def test_priority_change(self, client, make_task):
        t = make_task()
        data = client.patch(f"/api/tasks/{t['id']}", json={"priority": "high"}).json()
        assert data["priority"] == "high"

    def test_unknown_priority_rejected(self, client, make_task):
        t = make_task()
        res = client.patch(f"/api/tasks/{t['id']}", json={"priority": "critical"})
        assert res.status_code == 400

    def test_notes_set(self, client, make_task):
        t = make_task()
        data = client.patch(
            f"/api/tasks/{t['id']}", json={"notes": "important"}
        ).json()
        assert data["notes"] == "important"

    def test_notes_cleared_via_explicit_null(self, client, make_task):
        t = make_task(notes="original")
        data = client.patch(f"/api/tasks/{t['id']}", json={"notes": None}).json()
        assert data["notes"] is None

    def test_notes_cleared_via_whitespace_only(self, client, make_task):
        t = make_task(notes="original")
        data = client.patch(f"/api/tasks/{t['id']}", json={"notes": "   "}).json()
        assert data["notes"] is None

    def test_schedule_set(self, client, make_task):
        t = make_task()
        sched = {"date": "2026-05-20", "startMin": 540, "durationMin": 60}
        data = client.patch(f"/api/tasks/{t['id']}", json={"schedule": sched}).json()
        assert data["schedule"] == sched

    def test_schedule_cleared_via_explicit_null(self, client, make_task):
        t = make_task(
            schedule={"date": "2026-05-20", "startMin": 540, "durationMin": 60}
        )
        data = client.patch(f"/api/tasks/{t['id']}", json={"schedule": None}).json()
        assert data["schedule"] is None

    def test_absent_fields_are_preserved(self, client, make_task):
        # Critical contract: PATCH only touches keys present in the body.
        t = make_task(title="Original", priority="high", notes="kept")
        data = client.patch(f"/api/tasks/{t['id']}", json={"done": True}).json()
        assert data["title"] == "Original"
        assert data["priority"] == "high"
        assert data["notes"] == "kept"
        assert data["done"] is True

    def test_done_toggle_both_ways(self, client, make_task):
        t = make_task()
        assert (
            client.patch(f"/api/tasks/{t['id']}", json={"done": True}).json()["done"]
            is True
        )
        assert (
            client.patch(f"/api/tasks/{t['id']}", json={"done": False}).json()["done"]
            is False
        )

    def test_unknown_id_404(self, client):
        res = client.patch("/api/tasks/no-such-id", json={"title": "x"})
        assert res.status_code == 404

    def test_empty_body_is_noop(self, client, make_task):
        """An empty PATCH body returns the unchanged record (200, not 4xx).

        Documents the model_fields_set contract at the empty boundary:
        absent keys = "don't touch," so an empty body touches nothing.
        """
        t = make_task(title="Unchanged", priority="high", notes="kept")
        res = client.patch(f"/api/tasks/{t['id']}", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Unchanged"
        assert data["priority"] == "high"
        assert data["notes"] == "kept"

    def test_priority_explicit_null_is_rejected(self, client, make_task):
        """`priority: null` is a type error, not an "unset" instruction.

        Priority always has a value; if a caller wants to lower it, they pass
        a valid level. Sending null reaches validate_priority(None) → 400.
        """
        t = make_task()
        res = client.patch(f"/api/tasks/{t['id']}", json={"priority": None})
        assert res.status_code == 400

    # Removed: test_status_explicit_null_is_rejected — the status field
    # was dropped in Tier 2 #12. Legacy keys are silently ignored.

    def test_done_null_currently_coerces_to_false(self, client, make_task):
        """Documenting current behavior: PATCH done=null → done=False.

        This is bool(None) → False. If we ever decide null should be rejected,
        this test will flag the change so it's intentional.
        """
        t = make_task()
        client.patch(f"/api/tasks/{t['id']}", json={"done": True})
        res = client.patch(f"/api/tasks/{t['id']}", json={"done": None})
        assert res.status_code == 200
        assert res.json()["done"] is False


# --- DELETE /api/tasks/{id} -------------------------------------------------


@pytest.mark.unit
class TestDeleteTask:
    def test_delete_existing(self, client, make_task):
        t = make_task()
        res = client.delete(f"/api/tasks/{t['id']}")
        assert res.status_code == 200
        items = client.get("/api/tasks").json()["items"]
        assert all(it["id"] != t["id"] for it in items)

    def test_delete_unknown_returns_404(self, client):
        res = client.delete("/api/tasks/no-such-id")
        assert res.status_code == 404

    def test_delete_is_soft_delete(self, client, make_task, tmp_data_dir):
        # After DELETE the task should still exist on disk, but with
        # deletedAt set; GET filters it out. This is the soft-delete contract.
        import json

        t = make_task(title="soft-target")
        client.delete(f"/api/tasks/{t['id']}")
        on_disk = json.loads((tmp_data_dir / "tasks.json").read_text())
        target = next(i for i in on_disk["items"] if i["id"] == t["id"])
        assert target["deletedAt"] is not None
        assert isinstance(target["deletedAt"], float)

    def test_deleted_task_hidden_from_get_tasks(self, client, make_task):
        t = make_task(title="will be deleted")
        client.delete(f"/api/tasks/{t['id']}")
        items = client.get("/api/tasks").json()["items"]
        assert all(it["id"] != t["id"] for it in items)

    def test_deleted_task_hidden_from_day_view(self, client, make_task):
        t = make_task(
            schedule={"date": "2026-05-19", "startMin": 540, "durationMin": 30},
        )
        client.delete(f"/api/tasks/{t['id']}")
        tasks = client.get("/api/day/2026-05-19").json()["tasks"]
        assert tasks == []

    def test_delete_already_deleted_returns_404(self, client, make_task):
        t = make_task()
        client.delete(f"/api/tasks/{t['id']}")
        # Second DELETE: the task is filtered out of the "live" view, so
        # the API surface treats it as missing.
        res = client.delete(f"/api/tasks/{t['id']}")
        assert res.status_code == 404

    def test_patch_on_deleted_task_returns_404(self, client, make_task):
        t = make_task()
        client.delete(f"/api/tasks/{t['id']}")
        res = client.patch(f"/api/tasks/{t['id']}", json={"title": "new"})
        assert res.status_code == 404


# --- POST /api/tasks/{id}/restore -------------------------------------------


@pytest.mark.unit
class TestRestoreTask:
    def test_restore_round_trips(self, client, make_task):
        t = make_task(title="bring me back")
        client.delete(f"/api/tasks/{t['id']}")
        assert all(
            it["id"] != t["id"]
            for it in client.get("/api/tasks").json()["items"]
        )
        res = client.post(f"/api/tasks/{t['id']}/restore")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["id"] == t["id"]
        assert body["deletedAt"] is None
        items = client.get("/api/tasks").json()["items"]
        assert any(it["id"] == t["id"] for it in items)

    def test_restore_unknown_returns_404(self, client):
        res = client.post("/api/tasks/no-such-id/restore")
        assert res.status_code == 404

    def test_restore_live_task_is_idempotent(self, client, make_task):
        t = make_task()
        res = client.post(f"/api/tasks/{t['id']}/restore")
        assert res.status_code == 200
        assert res.json()["deletedAt"] is None


# --- A2: updatedAt + completedAt timestamps ---------------------------------


@pytest.mark.unit
class TestTimestamps:
    def test_post_sets_updated_at_equal_to_created_at(self, client):
        data = client.post("/api/tasks", json={"title": "fresh"}).json()
        assert data["updatedAt"] == data["createdAt"]
        assert data["completedAt"] is None

    def test_post_with_done_true_sets_completed_at(self, client):
        data = client.post(
            "/api/tasks", json={"title": "already done", "done": True}
        ).json()
        assert data["done"] is True
        assert data["completedAt"] == data["createdAt"]

    def test_patch_bumps_updated_at(self, client, make_task):
        import time

        t = make_task(title="orig")
        # Small sleep so the wall-clock advances measurably between POST/PATCH.
        time.sleep(0.01)
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"title": "renamed"}
        ).json()
        assert patched["updatedAt"] > t["updatedAt"]
        # createdAt is immutable.
        assert patched["createdAt"] == t["createdAt"]

    def test_patch_no_op_done_does_not_change_completed_at(
        self, client, make_task
    ):
        t = make_task(done=False)
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"title": "renamed"}
        ).json()
        assert patched["completedAt"] is None

    def test_done_false_to_true_sets_completed_at(self, client, make_task):
        t = make_task(done=False)
        assert t["completedAt"] is None
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"done": True}
        ).json()
        assert patched["done"] is True
        assert isinstance(patched["completedAt"], float)
        assert patched["completedAt"] >= patched["createdAt"]

    def test_done_true_to_false_clears_completed_at(self, client, make_task):
        t = make_task(done=True)
        assert t["completedAt"] is not None
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"done": False}
        ).json()
        assert patched["done"] is False
        assert patched["completedAt"] is None

    def test_done_explicit_same_value_is_a_no_op_for_completed_at(
        self, client, make_task
    ):
        # PATCH done=True on an already-done task: completedAt stays put.
        t = make_task(done=True)
        original = t["completedAt"]
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"done": True}
        ).json()
        assert patched["completedAt"] == original

    def test_legacy_task_without_updated_at_reads_with_filled_value(
        self, client, tmp_data_dir
    ):
        """Records written before A2 lack updatedAt — GET fills it in."""
        import json

        legacy = {
            "items": [
                {
                    "id": "legacy-1",
                    "title": "pre-A2",
                    "status": "active",
                    "priority": "medium",
                    "notes": None,
                    "schedule": None,
                    "done": False,
                    "createdAt": 1_000_000.0,
                }
            ]
        }
        (tmp_data_dir / "tasks.json").write_text(json.dumps(legacy))
        items = client.get("/api/tasks").json()["items"]
        assert len(items) == 1
        assert items[0]["updatedAt"] == 1_000_000.0
        assert items[0]["completedAt"] is None

    def test_legacy_task_patch_succeeds_and_fills_timestamps(
        self, client, tmp_data_dir
    ):
        import json

        legacy = {
            "items": [
                {
                    "id": "legacy-2",
                    "title": "pre-A2",
                    "status": "active",
                    "priority": "medium",
                    "notes": None,
                    "schedule": None,
                    "done": False,
                    "createdAt": 1_000_000.0,
                }
            ]
        }
        (tmp_data_dir / "tasks.json").write_text(json.dumps(legacy))
        res = client.patch("/api/tasks/legacy-2", json={"title": "now-renamed"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["title"] == "now-renamed"
        assert body["updatedAt"] > 1_000_000.0
        assert body["completedAt"] is None


# --- A5: tags placeholder field --------------------------------------------


@pytest.mark.unit
class TestTags:
    def test_post_default_is_empty_list(self, client):
        data = client.post("/api/tasks", json={"title": "no tags"}).json()
        assert data["tags"] == []

    def test_post_with_tags_round_trips(self, client):
        data = client.post(
            "/api/tasks", json={"title": "tagged", "tags": ["focus", "deep-work"]}
        ).json()
        assert data["tags"] == ["focus", "deep-work"]

    def test_patch_tags_replaces_existing(self, client, make_task):
        t = make_task(tags=["old-a", "old-b"])
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"tags": ["new"]}
        ).json()
        assert patched["tags"] == ["new"]

    def test_patch_tags_empty_clears(self, client, make_task):
        t = make_task(tags=["keep-me"])
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"tags": []}
        ).json()
        assert patched["tags"] == []

    def test_patch_without_tags_field_leaves_tags_alone(self, client, make_task):
        t = make_task(tags=["sticky"])
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"title": "renamed"}
        ).json()
        assert patched["tags"] == ["sticky"]

    def test_legacy_task_without_tags_reads_with_empty_list(
        self, client, tmp_data_dir
    ):
        import json

        legacy = {
            "items": [
                {
                    "id": "legacy-tag",
                    "title": "pre-A5",
                    "status": "active",
                    "priority": "medium",
                    "notes": None,
                    "schedule": None,
                    "done": False,
                    "createdAt": 1_000_000.0,
                }
            ]
        }
        (tmp_data_dir / "tasks.json").write_text(json.dumps(legacy))
        items = client.get("/api/tasks").json()["items"]
        assert items[0]["tags"] == []


# --- A6: persistent defaultDurationMin -------------------------------------


@pytest.mark.unit
class TestDefaultDurationMin:
    def test_post_default_is_30(self, client):
        data = client.post("/api/tasks", json={"title": "no slot"}).json()
        assert data["defaultDurationMin"] == 30

    def test_post_with_schedule_syncs_default_duration(self, client):
        data = client.post(
            "/api/tasks",
            json={
                "title": "scheduled at create",
                "schedule": {"date": "2026-05-20", "startMin": 540, "durationMin": 90},
            },
        ).json()
        assert data["defaultDurationMin"] == 90

    def test_post_explicit_default_duration_overrides_schedule(self, client):
        data = client.post(
            "/api/tasks",
            json={
                "title": "explicit wins",
                "schedule": {"date": "2026-05-20", "startMin": 540, "durationMin": 60},
                "defaultDurationMin": 45,
            },
        ).json()
        # Explicit field takes precedence over the schedule-derived sync.
        assert data["defaultDurationMin"] == 45

    def test_patch_schedule_duration_syncs_default(self, client, make_task):
        t = make_task(
            schedule={"date": "2026-05-20", "startMin": 540, "durationMin": 30}
        )
        assert t["defaultDurationMin"] == 30
        patched = client.patch(
            f"/api/tasks/{t['id']}",
            json={
                "schedule": {
                    "date": "2026-05-20",
                    "startMin": 540,
                    "durationMin": 90,
                }
            },
        ).json()
        assert patched["schedule"]["durationMin"] == 90
        assert patched["defaultDurationMin"] == 90

    def test_unscheduling_preserves_default_duration(self, client, make_task):
        t = make_task(
            schedule={"date": "2026-05-20", "startMin": 540, "durationMin": 75}
        )
        assert t["defaultDurationMin"] == 75
        # Unschedule by setting schedule to null.
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"schedule": None}
        ).json()
        assert patched["schedule"] is None
        assert patched["defaultDurationMin"] == 75

    def test_patch_default_duration_explicit(self, client, make_task):
        t = make_task()  # default 30
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"defaultDurationMin": 50}
        ).json()
        assert patched["defaultDurationMin"] == 50

    def test_default_duration_out_of_range_rejected(self, client, make_task):
        t = make_task()
        too_big = client.patch(
            f"/api/tasks/{t['id']}", json={"defaultDurationMin": 0}
        )
        assert too_big.status_code == 422

    def test_legacy_unscheduled_task_reads_with_30(self, client, tmp_data_dir):
        import json

        legacy = {
            "items": [
                {
                    "id": "legacy-dur-1",
                    "title": "pre-A6 unscheduled",
                    "status": "active",
                    "priority": "medium",
                    "notes": None,
                    "schedule": None,
                    "done": False,
                    "createdAt": 1_000_000.0,
                }
            ]
        }
        (tmp_data_dir / "tasks.json").write_text(json.dumps(legacy))
        items = client.get("/api/tasks").json()["items"]
        assert items[0]["defaultDurationMin"] == 30

    def test_legacy_v1_task_reads_with_normalized_new_fields(
        self, client, tmp_data_dir
    ):
        """A pre-Tier-2-#12 (schema v1) task with `status` set and missing
        the new fields reads back without status and with defaults for
        `dueDate` / `recurring` / `snoozedUntil`."""
        import json

        legacy = {
            "version": 1,
            "items": [
                {
                    "id": "legacy-v1",
                    "title": "pre-v2",
                    "status": "not_today",
                    "priority": "medium",
                    "notes": None,
                    "schedule": None,
                    "done": False,
                    "createdAt": 1_000_000.0,
                    "updatedAt": 1_000_000.0,
                    "completedAt": None,
                    "tags": [],
                    "defaultDurationMin": 30,
                }
            ],
        }
        (tmp_data_dir / "tasks.json").write_text(json.dumps(legacy))
        items = client.get("/api/tasks").json()["items"]
        assert "status" not in items[0]
        assert items[0]["dueDate"] is None
        assert items[0]["recurring"] is False
        assert items[0]["snoozedUntil"] is None


    def test_legacy_scheduled_task_reads_with_schedule_duration(
        self, client, tmp_data_dir
    ):
        """Pre-A6 task with a schedule.durationMin uses that as its preferred
        duration — so a previously-resized task remembers its size even though
        the new field was never written."""
        import json

        legacy = {
            "items": [
                {
                    "id": "legacy-dur-2",
                    "title": "pre-A6 resized",
                    "status": "active",
                    "priority": "medium",
                    "notes": None,
                    "schedule": {
                        "date": "2026-05-20",
                        "startMin": 540,
                        "durationMin": 120,
                    },
                    "done": False,
                    "createdAt": 1_000_000.0,
                }
            ]
        }
        (tmp_data_dir / "tasks.json").write_text(json.dumps(legacy))
        items = client.get("/api/tasks").json()["items"]
        assert items[0]["defaultDurationMin"] == 120


# --- GET /api/tasks ---------------------------------------------------------


@pytest.mark.unit
class TestListTasks:
    def test_empty_store_returns_empty(self, client):
        assert client.get("/api/tasks").json() == {"items": []}

    def test_newest_first(self, client):
        # Three sequential POSTs — TestClient HTTP overhead makes createdAt
        # values monotonically increase.
        a = client.post("/api/tasks", json={"title": "first"}).json()
        b = client.post("/api/tasks", json={"title": "second"}).json()
        c = client.post("/api/tasks", json={"title": "third"}).json()
        ids = [t["id"] for t in client.get("/api/tasks").json()["items"]]
        assert ids[0] == c["id"]
        assert ids[1] == b["id"]
        assert ids[2] == a["id"]


# --- GET /api/day/{date} ----------------------------------------------------


@pytest.mark.unit
class TestDayView:
    def test_filters_to_matching_date_only(self, client, make_task):
        make_task(title="unscheduled")
        on_today = make_task(
            title="today",
            schedule={"date": "2026-05-19", "startMin": 540, "durationMin": 30},
        )
        make_task(
            title="other day",
            schedule={"date": "2026-05-20", "startMin": 540, "durationMin": 30},
        )
        items = client.get("/api/day/2026-05-19").json()["tasks"]
        assert [t["id"] for t in items] == [on_today["id"]]

    def test_empty_day_returns_empty_list(self, client):
        assert client.get("/api/day/2026-01-01").json() == {"tasks": []}

    def test_bad_date_format_rejected(self, client):
        res = client.get("/api/day/not-a-date")
        assert res.status_code == 400

    def test_partial_date_rejected(self, client):
        res = client.get("/api/day/2026-5-19")
        assert res.status_code == 400


# --- Tier 2 #12: new fields + recurring-aware completedAt ----------------


@pytest.mark.unit
class TestNewSchemaFields:
    def test_post_with_due_date(self, client):
        data = client.post(
            "/api/tasks", json={"title": "submit form", "dueDate": "2026-12-31"}
        ).json()
        assert data["dueDate"] == "2026-12-31"

    def test_due_date_bad_format_rejected(self, client):
        res = client.post(
            "/api/tasks", json={"title": "x", "dueDate": "not-a-date"}
        )
        assert res.status_code == 422

    def test_due_date_partial_format_rejected(self, client):
        res = client.post(
            "/api/tasks", json={"title": "x", "dueDate": "2026-5-1"}
        )
        assert res.status_code == 422

    def test_patch_due_date_clear_via_null(self, client, make_task):
        t = make_task(dueDate="2026-12-31")
        assert t["dueDate"] == "2026-12-31"
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"dueDate": None}
        ).json()
        assert patched["dueDate"] is None

    def test_post_with_recurring(self, client):
        data = client.post(
            "/api/tasks", json={"title": "practice piano", "recurring": True}
        ).json()
        assert data["recurring"] is True

    def test_patch_toggle_recurring(self, client, make_task):
        t = make_task(recurring=False)
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"recurring": True}
        ).json()
        assert patched["recurring"] is True

    def test_post_with_snoozed_until(self, client):
        ts = 9_999_999_999.0
        data = client.post(
            "/api/tasks", json={"title": "later", "snoozedUntil": ts}
        ).json()
        assert data["snoozedUntil"] == ts

    def test_patch_snoozed_until_clear_via_null(self, client, make_task):
        t = make_task(snoozedUntil=9_999_999_999.0)
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"snoozedUntil": None}
        ).json()
        assert patched["snoozedUntil"] is None


@pytest.mark.unit
class TestRecurringDoneSemantics:
    def test_non_recurring_done_idempotent_completedAt_unchanged(
        self, client, make_task
    ):
        """Pre-existing contract preserved: PATCH done:true twice on a
        non-recurring task leaves completedAt at the first transition."""
        t = make_task(done=True)
        original = t["completedAt"]
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"done": True}
        ).json()
        assert patched["completedAt"] == original

    def test_recurring_done_refreshes_completedAt_each_patch(
        self, client, make_task
    ):
        """A recurring task gets a fresh completedAt on every done-true
        PATCH so the wins counter can pick up a new day's completion
        without the client needing to PATCH done:false first."""
        import time as _time

        t = make_task(recurring=True, done=True)
        first = t["completedAt"]
        assert isinstance(first, float)
        _time.sleep(0.01)
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"done": True}
        ).json()
        assert patched["completedAt"] > first

    def test_recurring_patch_done_false_clears_completedAt(
        self, client, make_task
    ):
        t = make_task(recurring=True, done=True)
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"done": False}
        ).json()
        assert patched["done"] is False
        assert patched["completedAt"] is None


# --- Tier 2 #15: sticky-time recurrence (recurSchedule / recurExceptions) ---


@pytest.mark.unit
class TestRecurSchedule:
    def test_post_default_recur_fields(self, client):
        data = client.post("/api/tasks", json={"title": "x"}).json()
        assert data["recurSchedule"] is None
        assert data["recurExceptions"] == []

    def test_post_with_recur_schedule_round_trips(self, client):
        body = {
            "title": "standup",
            "recurSchedule": {
                "startMin": 540,
                "durationMin": 15,
                "days": ["mon", "tue", "wed", "thu", "fri"],
            },
        }
        data = client.post("/api/tasks", json=body).json()
        assert data["recurSchedule"] == body["recurSchedule"]

    def test_post_recur_schedule_every_day_uses_null_days(self, client):
        body = {
            "title": "meds",
            "recurSchedule": {"startMin": 480, "durationMin": 5, "days": None},
        }
        data = client.post("/api/tasks", json=body).json()
        assert data["recurSchedule"]["days"] is None

    def test_invalid_weekday_token_rejected(self, client):
        res = client.post(
            "/api/tasks",
            json={
                "title": "x",
                "recurSchedule": {"startMin": 0, "durationMin": 30, "days": ["monday"]},
            },
        )
        assert res.status_code == 422

    def test_recur_schedule_out_of_range_start_rejected(self, client):
        res = client.post(
            "/api/tasks",
            json={
                "title": "x",
                "recurSchedule": {"startMin": 99999, "durationMin": 30, "days": None},
            },
        )
        assert res.status_code == 422

    def test_patch_set_recur_schedule(self, client, make_task):
        t = make_task()
        spec = {"startMin": 600, "durationMin": 45, "days": ["sat", "sun"]}
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"recurSchedule": spec}
        ).json()
        assert patched["recurSchedule"] == spec

    def test_patch_clear_recur_schedule_via_null(self, client, make_task):
        t = make_task(
            recurSchedule={"startMin": 540, "durationMin": 30, "days": None}
        )
        assert t["recurSchedule"] is not None
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"recurSchedule": None}
        ).json()
        assert patched["recurSchedule"] is None

    def test_recur_exceptions_replace_all(self, client, make_task):
        t = make_task()
        patched = client.patch(
            f"/api/tasks/{t['id']}",
            json={"recurExceptions": ["2026-06-01", "2026-06-08"]},
        ).json()
        assert patched["recurExceptions"] == ["2026-06-01", "2026-06-08"]
        patched2 = client.patch(
            f"/api/tasks/{t['id']}", json={"recurExceptions": ["2026-06-01"]}
        ).json()
        assert patched2["recurExceptions"] == ["2026-06-01"]

    def test_recur_exceptions_bad_date_rejected(self, client, make_task):
        t = make_task()
        res = client.patch(
            f"/api/tasks/{t['id']}", json={"recurExceptions": ["June 1"]}
        )
        assert res.status_code == 422

    def test_patch_without_recur_fields_leaves_them_alone(self, client, make_task):
        t = make_task(
            recurSchedule={"startMin": 540, "durationMin": 30, "days": ["mon"]},
        )
        patched = client.patch(
            f"/api/tasks/{t['id']}", json={"title": "renamed"}
        ).json()
        assert patched["recurSchedule"] == {
            "startMin": 540,
            "durationMin": 30,
            "days": ["mon"],
        }

    def test_legacy_v2_task_reads_with_normalized_recur_fields(
        self, client, tmp_data_dir
    ):
        """A pre-#15 (v2) task on disk gets recurSchedule/recurExceptions
        backfilled on read without an explicit migration write."""
        import json
        import server

        legacy = {
            "id": "old",
            "title": "legacy v2",
            "priority": "medium",
            "schedule": None,
            "done": False,
            "createdAt": 1.0,
            "updatedAt": 1.0,
        }
        (tmp_data_dir / "tasks.json").write_text(
            json.dumps({"version": 2, "items": [legacy]})
        )
        items = client.get("/api/tasks").json()["items"]
        assert items[0]["recurSchedule"] is None
        assert items[0]["recurExceptions"] == []
