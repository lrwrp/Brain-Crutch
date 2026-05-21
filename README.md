# ADHD assistant

A local-first single-user webpage for taming the day. Day-timeline +
tasks tab + quick-capture inbox, all stored as JSON files next to the
server. Nothing leaves your machine — no accounts, no cloud, no sync.

## Quickstart

You need [`uv`](https://docs.astral.sh/uv/) on your PATH. If you don't
have it:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or on Windows (PowerShell):
#   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then:

```sh
./run.sh        # macOS / Linux
run.bat         # Windows
```

First launch creates a `.venv/` and installs the four dependencies
(FastAPI, uvicorn, icalendar, recurring-ical-events). After that the
script just starts the server and opens <http://localhost:1440> in your
browser.

## What's where

| Path                       | Purpose                                       |
|----------------------------|-----------------------------------------------|
| `data/tasks.json`          | All tasks (auto-created on first launch)      |
| `data/inbox.json`          | Quick-capture inbox                           |
| `data/days/`               | Legacy per-day storage (folded into tasks)    |
| `data/UserCalendar/*.ics`  | Drop calendar exports here for read-only overlay |
| `server.py`                | FastAPI app + JSON storage                    |
| `web/`                     | Frontend (plain HTML/CSS/ES modules)          |

The calendar overlay is one-way: events from `.ics` files appear on the
timeline as a translucent backdrop. The assistant never writes back.

To utilize the calendar overlay, drop an exported .ics from your calendar
into data/UserCalendar/

## Keyboard shortcuts

- `\t` — capture a task (slash-command modal)
- `\n` — capture an inbox note
- `\f` — start a focus timer
- `c` — toggle done on the selected task
- `w` / `s` — nudge selected task earlier / later
- `a` / `d` — shrink / grow selected task duration
- `r` / `e` — read / edit selected task's notes
- `←` / `→` — previous / next day

## Backup

Everything is `data/`. Copy the folder, you've got a backup. Replace it
to restore.

## Manual setup (if `run.sh` isn't your thing)

```sh
uv venv --python 3.11        # 3.11+ works; uv will fetch one if needed
uv pip install -r requirements.txt
.venv/bin/python server.py
```

## Development

Tests use pytest + pytest-playwright:

```sh
uv pip install -r requirements-dev.txt
uv run playwright install chromium
make test           # unit + server tests
make test-e2e       # browser tests (slower)
make test-all       # everything
```
