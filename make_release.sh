#!/usr/bin/env bash
# Produce a shippable tarball of the ADHD assistant.
#
# Output: dist/adhd-assistant-YYYYMMDD.tar.gz
# Exclusions: developer artefacts (.git, .venv, __pycache__), the user's
# private data/ directory, internal notes (TODO.md, ARCHITECTURE.md,
# CONTEXT.md, memory/agent dirs), and the tests/ tree.
#
# The recipient should be able to extract the tarball anywhere, run
# ./run.sh (or run.bat on Windows), and be up in under a minute.
set -euo pipefail

cd "$(dirname "$0")"

NAME="adhd-assistant"
STAMP="$(date +%Y%m%d)"
ROOT="${NAME}-${STAMP}"
OUT="dist/${ROOT}.tar.gz"

mkdir -p dist
rm -rf "dist/${ROOT}"

# Files to ship — everything the recipient needs to run, nothing else.
# Listed explicitly (not "everything except…") so it's obvious what
# leaves the machine.
INCLUDE=(
  server.py
  storage.py
  calendar_overlay.py
  pyproject.toml
  uv.lock
  run.sh
  run.bat
  README.md
  web
)

# Stage into dist/${ROOT}/ then tar from there, so the archive unpacks
# into a single sensibly-named directory.
mkdir -p "dist/${ROOT}"
for item in "${INCLUDE[@]}"; do
  if [ ! -e "$item" ]; then
    echo "WARNING: $item missing, skipping" >&2
    continue
  fi
  cp -R "$item" "dist/${ROOT}/"
done

# Drop any stale __pycache__ that snuck in via the copy.
find "dist/${ROOT}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "dist/${ROOT}" -name '*.pyc' -delete 2>/dev/null || true
find "dist/${ROOT}" -name '.DS_Store' -delete 2>/dev/null || true

# Make sure run.sh stays executable through the tarball.
chmod +x "dist/${ROOT}/run.sh"

tar -czf "$OUT" -C dist "$ROOT"
rm -rf "dist/${ROOT}"

ls -lh "$OUT"
echo ""
echo "Release tarball: $OUT"
echo "Recipient runs: tar -xzf ${ROOT}.tar.gz && cd ${ROOT} && ./run.sh"
