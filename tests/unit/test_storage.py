"""Tests for ``server`` storage primitives: ``read_json``, ``write_json``, ``new_id``.

These are the bedrock of every persistent operation. Failure to be atomic here
corrupts user data — the tests verify the temp-file + ``os.replace`` dance
holds up under both ``os.replace`` failures and serialization failures.
"""

from __future__ import annotations

import json
import os
import re

import pytest

import server


# --- read_json --------------------------------------------------------------


@pytest.mark.unit
class TestReadJson:
    def test_reads_valid_file(self, tmp_path):
        p = tmp_path / "in.json"
        p.write_text('{"hello": "world", "n": 3}')
        assert server.read_json(p) == {"hello": "world", "n": 3}

    def test_missing_file_raises_filenotfounderror(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            server.read_json(tmp_path / "missing.json")


# --- write_json -------------------------------------------------------------


@pytest.mark.unit
class TestWriteJson:
    def test_creates_new_file(self, tmp_path):
        p = tmp_path / "new.json"
        server.write_json(p, {"items": [1, 2, 3]})
        assert p.exists()
        assert json.loads(p.read_text()) == {"items": [1, 2, 3]}

    def test_overwrites_existing_file(self, tmp_path):
        p = tmp_path / "existing.json"
        p.write_text('{"old": true}')
        server.write_json(p, {"new": True})
        assert json.loads(p.read_text()) == {"new": True}

    def test_atomic_rename_failure_preserves_original(self, tmp_path, monkeypatch):
        """If os.replace fails partway, the existing file must be intact."""
        p = tmp_path / "guarded.json"
        p.write_text('{"original": true}')

        def boom(*args, **kwargs):
            raise OSError("simulated atomic-rename failure")

        monkeypatch.setattr("os.replace", boom)

        with pytest.raises(OSError, match="simulated"):
            server.write_json(p, {"new_content": "would replace original"})

        assert json.loads(p.read_text()) == {"original": True}

    def test_temp_file_cleaned_up_on_rename_failure(self, tmp_path, monkeypatch):
        p = tmp_path / "out.json"

        def boom(*args, **kwargs):
            raise OSError("nope")

        monkeypatch.setattr("os.replace", boom)

        with pytest.raises(OSError):
            server.write_json(p, {"items": []})

        leftovers = [c for c in tmp_path.iterdir() if c.name.startswith(".tmp-")]
        assert leftovers == [], f"temp files lingered: {leftovers}"

    def test_temp_file_cleaned_up_on_serialize_failure(self, tmp_path):
        """A non-JSON-serializable payload raises during json.dump, before
        os.replace is called. The temp file must still be cleaned up."""
        p = tmp_path / "out.json"
        bad = {"items": [{1, 2, 3}]}  # sets are not JSON serializable

        with pytest.raises(TypeError):
            server.write_json(p, bad)

        # Target was never created.
        assert not p.exists()
        # And no .tmp-* leftovers.
        leftovers = [c for c in tmp_path.iterdir() if c.name.startswith(".tmp-")]
        assert leftovers == []

    def test_emits_indented_utf8_json(self, tmp_path):
        p = tmp_path / "utf8.json"
        server.write_json(p, {"greeting": "héllo — 世界"})
        text = p.read_text(encoding="utf-8")
        # Indented (multi-line) and UTF-8 (non-ASCII characters preserved).
        assert "\n" in text
        assert "héllo" in text
        assert "世界" in text


# --- new_id -----------------------------------------------------------------


@pytest.mark.unit
class TestNewId:
    def test_returns_string(self):
        assert isinstance(server.new_id(), str)

    def test_returns_distinct_ids_in_bulk(self):
        ids = {server.new_id() for _ in range(200)}
        assert len(ids) == 200

    def test_ids_are_url_safe_charset(self):
        for _ in range(20):
            assert re.fullmatch(r"[A-Za-z0-9_-]+", server.new_id())


# --- A3: load_versioned / save_versioned -----------------------------------


@pytest.mark.unit
class TestVersionedIO:
    def test_save_versioned_stamps_current_version(self, tmp_path):
        p = tmp_path / "out.json"
        server.save_versioned(p, {"items": [{"id": "a"}]})
        on_disk = json.loads(p.read_text())
        assert on_disk["version"] == server.CURRENT_VERSION
        assert on_disk["items"] == [{"id": "a"}]

    def test_save_versioned_does_not_mutate_caller_payload(self, tmp_path):
        payload = {"items": []}
        server.save_versioned(tmp_path / "x.json", payload)
        # Caller's dict must remain unstamped — versioning is an IO-layer
        # concern, not a payload concern.
        assert "version" not in payload

    def test_load_versioned_returns_current_when_already_current(self, tmp_path):
        p = tmp_path / "in.json"
        p.write_text(json.dumps({"version": server.CURRENT_VERSION, "items": [1]}))
        result = server.load_versioned(p)
        assert result["version"] == server.CURRENT_VERSION
        assert result["items"] == [1]

    def test_load_versioned_upgrades_legacy_v0_and_persists(self, tmp_path):
        # Pre-A3 file: bare {"items": [...]} with no version key.
        p = tmp_path / "legacy.json"
        p.write_text(json.dumps({"items": [{"id": "x"}]}))

        result = server.load_versioned(p)
        assert result["version"] == server.CURRENT_VERSION
        assert result["items"] == [{"id": "x"}]

        # Upgrade should have been written back to disk.
        on_disk = json.loads(p.read_text())
        assert on_disk["version"] == server.CURRENT_VERSION

    def test_load_versioned_does_not_rewrite_when_already_current(
        self, tmp_path, monkeypatch
    ):
        p = tmp_path / "in.json"
        p.write_text(json.dumps({"version": server.CURRENT_VERSION, "items": []}))

        writes = []
        original_write = server.write_json
        monkeypatch.setattr(
            server,
            "write_json",
            lambda path, payload: writes.append(path) or original_write(path, payload),
        )

        server.load_versioned(p)
        assert writes == [], "load_versioned should not write when already current"

    def test_load_versioned_refuses_future_version(self, tmp_path):
        p = tmp_path / "future.json"
        p.write_text(
            json.dumps({"version": server.CURRENT_VERSION + 1, "items": []})
        )
        with pytest.raises(RuntimeError, match="supports up to"):
            server.load_versioned(p)

    def test_load_versioned_v1_to_v2_drops_status_field(self, tmp_path):
        """Tier 2 #12: the v1→v2 upgrade strips the legacy ``status`` key
        from each item and bumps the version."""
        p = tmp_path / "legacy_v1.json"
        p.write_text(
            json.dumps(
                {
                    "version": 1,
                    "items": [
                        {"id": "a", "title": "alpha", "status": "active"},
                        {"id": "b", "title": "beta", "status": "not_today"},
                    ],
                }
            )
        )

        result = server.load_versioned(p)
        # The upgrade chain runs all the way to the current version; the
        # v1→v2 effect we care about is that ``status`` is gone.
        assert result["version"] == server.CURRENT_VERSION
        for item in result["items"]:
            assert "status" not in item

        on_disk = json.loads(p.read_text())
        assert on_disk["version"] == server.CURRENT_VERSION
        for item in on_disk["items"]:
            assert "status" not in item

    def test_load_versioned_v2_to_v3_bumps_version(self, tmp_path):
        """Tier 2 #15: the v2→v3 upgrade is a pure version bump (recur fields
        are backfilled lazily by _normalize_task, not written here), so a v2
        file becomes current-versioned with items untouched."""
        p = tmp_path / "legacy_v2.json"
        p.write_text(
            json.dumps(
                {
                    "version": 2,
                    "items": [{"id": "a", "title": "alpha"}],
                }
            )
        )

        result = server.load_versioned(p)
        assert result["version"] == server.CURRENT_VERSION
        # Items are not rewritten by the bump; recur fields are absent on disk
        # and filled on task read instead.
        assert result["items"] == [{"id": "a", "title": "alpha"}]

        on_disk = json.loads(p.read_text())
        assert on_disk["version"] == server.CURRENT_VERSION

    def test_ensure_data_stamps_fresh_files_with_version(self, tmp_data_dir):
        # tmp_data_dir already pointed server's paths at an empty dir; trigger
        # ensure_data and confirm both files land on disk with version stamped.
        server.ensure_data()

        inbox = json.loads((tmp_data_dir / "inbox.json").read_text())
        tasks = json.loads((tmp_data_dir / "tasks.json").read_text())
        assert inbox["version"] == server.CURRENT_VERSION
        assert tasks["version"] == server.CURRENT_VERSION
        assert inbox["items"] == []
        assert tasks["items"] == []

    def test_ensure_data_upgrades_existing_legacy_files(self, tmp_data_dir):
        # Seed legacy (unversioned) files, then run ensure_data and confirm
        # the version key is written.
        (tmp_data_dir / "inbox.json").write_text(json.dumps({"items": []}))
        (tmp_data_dir / "tasks.json").write_text(
            json.dumps({"items": [{"id": "legacy"}]})
        )

        server.ensure_data()

        inbox = json.loads((tmp_data_dir / "inbox.json").read_text())
        tasks = json.loads((tmp_data_dir / "tasks.json").read_text())
        assert inbox["version"] == server.CURRENT_VERSION
        assert tasks["version"] == server.CURRENT_VERSION
        # Legacy items preserved verbatim.
        assert tasks["items"] == [{"id": "legacy"}]
