.PHONY: test test-all test-watch test-e2e run

# Fast tier: unit + integration server tests via FastAPI TestClient.
test:
	uv run pytest -m "not e2e"

# Everything, including E2E browser tests.
test-all:
	uv run pytest

# E2E only — useful while iterating on browser tests.
test-e2e:
	uv run pytest -m e2e

# Rerun the fast tier on file change. Requires `pytest-watch` (install on demand).
test-watch:
	uv run ptw -- -m "not e2e"

# Boot the dev server. `uv run` auto-syncs if pyproject.toml/uv.lock
# changed since last invocation.
run:
	uv run --no-dev python server.py
