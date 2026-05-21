"""Tests for the inbox HTTP API.

Covers POST/GET/DELETE ``/api/inbox`` including the URL-detection rule on
capture (leading ``http(s)://`` only).
"""

from __future__ import annotations

import pytest


# --- POST /api/inbox --------------------------------------------------------


@pytest.mark.unit
class TestCreateInbox:
    def test_basic_text(self, client):
        res = client.post("/api/inbox", json={"text": "remember the milk"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["text"] == "remember the milk"
        assert data["url"] is None
        assert data["title"] is None
        assert isinstance(data["id"], str) and data["id"]
        assert isinstance(data["createdAt"], float)

    def test_leading_http_url_detected(self, client):
        data = client.post("/api/inbox", json={"text": "http://example.com"}).json()
        assert data["url"] == "http://example.com"

    def test_leading_https_url_detected(self, client):
        data = client.post(
            "/api/inbox", json={"text": "https://example.com/article"}
        ).json()
        assert data["url"] == "https://example.com/article"

    def test_url_with_trailing_text(self, client):
        # URL is the first whitespace-separated token; trailing text is kept
        # in `text` but not in `url`.
        data = client.post(
            "/api/inbox", json={"text": "https://example.com check it out"}
        ).json()
        assert data["url"] == "https://example.com"
        assert data["text"] == "https://example.com check it out"

    def test_url_detection_is_only_at_leading_position(self, client):
        # No URL detected because the URL doesn't sit at the start.
        data = client.post(
            "/api/inbox", json={"text": "see this https://example.com"}
        ).json()
        assert data["url"] is None
        assert data["text"] == "see this https://example.com"

    def test_url_detection_is_case_insensitive(self, client):
        # Prefix check uses .lower() — uppercase scheme still detected.
        data = client.post("/api/inbox", json={"text": "HTTPS://EXAMPLE.com"}).json()
        # url is the verbatim first token, preserving original casing.
        assert data["url"] == "HTTPS://EXAMPLE.com"

    def test_text_stripped(self, client):
        data = client.post("/api/inbox", json={"text": "  trimmed  "}).json()
        assert data["text"] == "trimmed"

    def test_empty_text_rejected(self, client):
        res = client.post("/api/inbox", json={"text": ""})
        assert res.status_code == 400

    def test_whitespace_text_rejected(self, client):
        res = client.post("/api/inbox", json={"text": "   "})
        assert res.status_code == 400

    def test_client_supplied_id_is_ignored_server_mints_its_own(self, client):
        """A4: server-only IDs — a spoofed ``id`` in the body is dropped."""
        spoofed = "client-spoofed-id"
        data = client.post(
            "/api/inbox", json={"text": "honest capture", "id": spoofed}
        ).json()
        assert data["id"] != spoofed
        items = client.get("/api/inbox").json()["items"]
        assert all(it["id"] != spoofed for it in items)


# --- GET /api/inbox ---------------------------------------------------------


@pytest.mark.unit
class TestListInbox:
    def test_empty_returns_empty(self, client):
        assert client.get("/api/inbox").json() == {"items": []}

    def test_newest_first(self, client):
        a = client.post("/api/inbox", json={"text": "first"}).json()
        b = client.post("/api/inbox", json={"text": "second"}).json()
        c = client.post("/api/inbox", json={"text": "third"}).json()
        ids = [it["id"] for it in client.get("/api/inbox").json()["items"]]
        assert ids[0] == c["id"]
        assert ids[1] == b["id"]
        assert ids[2] == a["id"]


# --- DELETE /api/inbox/{id} -------------------------------------------------


@pytest.mark.unit
class TestDeleteInbox:
    def test_delete_existing(self, client, make_inbox):
        item = make_inbox()
        res = client.delete(f"/api/inbox/{item['id']}")
        assert res.status_code == 200
        items = client.get("/api/inbox").json()["items"]
        assert all(it["id"] != item["id"] for it in items)

    def test_delete_unknown_returns_404(self, client):
        res = client.delete("/api/inbox/no-such-id")
        assert res.status_code == 404

    def test_delete_is_soft_delete(self, client, make_inbox, tmp_data_dir):
        import json

        item = make_inbox("soft-target")
        client.delete(f"/api/inbox/{item['id']}")
        on_disk = json.loads((tmp_data_dir / "inbox.json").read_text())
        target = next(i for i in on_disk["items"] if i["id"] == item["id"])
        assert target["deletedAt"] is not None
        assert isinstance(target["deletedAt"], float)

    def test_delete_already_deleted_returns_404(self, client, make_inbox):
        item = make_inbox()
        client.delete(f"/api/inbox/{item['id']}")
        res = client.delete(f"/api/inbox/{item['id']}")
        assert res.status_code == 404


# --- POST /api/inbox/{id}/restore -------------------------------------------


@pytest.mark.unit
class TestRestoreInbox:
    def test_restore_round_trips(self, client, make_inbox):
        item = make_inbox("bring me back")
        client.delete(f"/api/inbox/{item['id']}")
        assert all(
            it["id"] != item["id"]
            for it in client.get("/api/inbox").json()["items"]
        )
        res = client.post(f"/api/inbox/{item['id']}/restore")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["id"] == item["id"]
        assert body["deletedAt"] is None
        items = client.get("/api/inbox").json()["items"]
        assert any(it["id"] == item["id"] for it in items)

    def test_restore_unknown_returns_404(self, client):
        res = client.post("/api/inbox/no-such-id/restore")
        assert res.status_code == 404

    def test_restore_live_item_is_idempotent(self, client, make_inbox):
        item = make_inbox()
        res = client.post(f"/api/inbox/{item['id']}/restore")
        assert res.status_code == 200
        assert res.json()["deletedAt"] is None
