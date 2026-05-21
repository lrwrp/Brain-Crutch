"""E2E fixtures: a real uvicorn process on a random port, per-test data dir.

Unit tests use ``TestClient`` against an in-process app with monkey-patched
data paths. E2E tests can't do that — Playwright drives a real browser, which
needs a real network endpoint. The ``live_server`` fixture spawns a uvicorn
subprocess with ``ADHD_DATA_DIR`` set so each test gets total isolation.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_url(url: str, *, timeout: float = 15.0) -> None:
    """Poll ``url`` until it responds 200, or raise after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                resp.read()
            return
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(
        f"server at {url} didn't become ready within {timeout}s "
        f"(last error: {last_err})"
    )


@pytest.fixture
def live_server(tmp_path):
    """Spawn ``uvicorn server:app`` on a random port with ADHD_DATA_DIR isolated."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    port = _find_free_port()
    env = os.environ.copy()
    env["ADHD_DATA_DIR"] = str(data_dir)
    # Force Python to not write bytecode in the repo root from the subprocess.
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_url(f"{base_url}/api/tasks", timeout=15)
    except Exception:
        proc.terminate()
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        raise RuntimeError(
            "live_server failed to start.\n"
            f"stdout: {out.decode(errors='replace')}\n"
            f"stderr: {err.decode(errors='replace')}"
        )

    yield SimpleNamespace(url=base_url, data_dir=data_dir, port=port)

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
