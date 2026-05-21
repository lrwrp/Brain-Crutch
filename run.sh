#!/usr/bin/env bash
# Bootstrap + launch the ADHD assistant.
#
# First run: creates .venv/, installs deps from requirements.txt, then
# starts the server and opens the browser. Subsequent runs skip setup
# (uv pip install is a fast no-op when nothing has changed).
set -euo pipefail

cd "$(dirname "$0")"

# --- uv check ----------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<EOF
uv is required to run this app. Install it with:

  curl -LsSf https://astral.sh/uv/install.sh | sh

Then re-run this script.
EOF
  exit 1
fi

# --- venv + deps -------------------------------------------------------
# Create .venv on first run. uv will fetch a Python 3.11+ interpreter if
# the system doesn't have one. The interpreter cache is shared across
# uv projects, so this is a one-time cost.
if [ ! -d .venv ]; then
  echo "Setting up virtualenv (one-time)…"
  uv venv --python 3.11
fi

# Idempotent — exits in <100ms when nothing's missing.
uv pip install --quiet -r requirements.txt

# --- launch ------------------------------------------------------------
URL="http://localhost:1440"

# Open the browser ~1s after the server starts. Run in the background so
# the foreground exec keeps stdout/stderr attached to the server.
(
  sleep 1
  if command -v open >/dev/null 2>&1; then
    open "$URL" || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" || true
  fi
) &

echo "Starting on $URL — Ctrl-C to stop."
exec .venv/bin/python server.py
