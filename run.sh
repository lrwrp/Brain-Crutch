#!/usr/bin/env bash
# Bootstrap + launch the ADHD assistant.
#
# `uv run` reads pyproject.toml + uv.lock, materializes .venv on first
# run (fetching a Python interpreter if needed), then exec's the
# command. Subsequent runs are a fast no-op when the lockfile hasn't
# moved. No separate install step needed.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<EOF
uv is required to run this app. Install it with:

  curl -LsSf https://astral.sh/uv/install.sh | sh

Then re-run this script.
EOF
  exit 1
fi

URL="http://localhost:1440"

# Open the browser ~1s after the server starts. Background so the
# foreground exec keeps stdout/stderr attached to the server.
(
  sleep 1
  if command -v open >/dev/null 2>&1; then
    open "$URL" || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" || true
  fi
) &

echo "Starting on $URL — Ctrl-C to stop."
exec uv run --no-dev python server.py

