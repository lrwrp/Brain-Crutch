"""Unit: LAN-hardening batch (code review follow-ups).

Three fixes, one file:
  - TrustedHost middleware — requests with a foreign Host header are rejected
    (the cheap DNS-rebinding guard), while loopback and Tailscale-serve hosts
    pass.
  - ``_read_activity`` tolerates an empty/corrupt activity.json instead of
    500-ing the momentum gauge.
  - ``_WRITE_LOCK`` serializes read-modify-write cycles so concurrent writers
    (phone + desktop) can't drop each other's updates.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient


# --- TrustedHost (DNS-rebinding guard) --------------------------------------


def _client_for_host(base_url: str) -> TestClient:
    import server

    return TestClient(server.app, base_url=base_url)


def test_foreign_host_rejected(tmp_data_dir):
    with _client_for_host("http://evil.example.com") as c:
        res = c.get("/api/tasks")
    assert res.status_code == 400


def test_loopback_hosts_allowed(tmp_data_dir):
    for base in ("http://localhost", "http://127.0.0.1"):
        with _client_for_host(base) as c:
            assert c.get("/api/tasks").status_code == 200


def test_tailscale_serve_host_allowed(tmp_data_dir):
    """`tailscale serve` proxies with Host = <machine>.<tailnet>.ts.net."""
    with _client_for_host("http://myserver.tail1234.ts.net") as c:
        assert c.get("/api/tasks").status_code == 200


def test_host_match_ignores_port(tmp_data_dir):
    with _client_for_host("http://localhost:1440") as c:
        assert c.get("/api/tasks").status_code == 200


# --- Corrupt activity.json tolerance ----------------------------------------


def test_empty_activity_file_reads_as_blank(client, tmp_data_dir):
    (tmp_data_dir / "activity.json").write_text("")
    res = client.get("/api/activity")
    assert res.status_code == 200
    assert res.json() == {"days": {}}


def test_corrupt_activity_file_recovers_on_post(client, tmp_data_dir):
    (tmp_data_dir / "activity.json").write_text("{not json")
    res = client.post("/api/activity")
    assert res.status_code == 200
    assert res.json()["count"] == 1  # log restarted cleanly from the ping


# --- Write lock (concurrent read-modify-write) ------------------------------


def test_concurrent_activity_posts_all_count(client):
    n = 30
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.post("/api/activity"), range(n)))
    assert all(r.status_code == 200 for r in results)
    days = client.get("/api/activity").json()["days"]
    assert sum(days.values()) == n  # no increment lost to interleaving


def test_concurrent_task_creates_all_persist(client):
    n = 20
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda i: client.post("/api/tasks", json={"title": f"task {i}"}),
                range(n),
            )
        )
    assert all(r.status_code == 200 for r in results)
    items = client.get("/api/tasks").json()["items"]
    assert len(items) == n  # no create lost to interleaving


def test_concurrent_patches_to_different_tasks_all_land(client, make_task):
    ids = [make_task(title=f"t{i}")["id"] for i in range(10)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda tid: client.patch(f"/api/tasks/{tid}", json={"done": True}),
                ids,
            )
        )
    assert all(r.status_code == 200 for r in results)
    items = client.get("/api/tasks").json()["items"]
    assert all(it["done"] for it in items)  # every PATCH survived
