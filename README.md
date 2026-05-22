# ADHD assistant

## IMPORTANT!  run.bat is UNTESTED, use at your own risk.
This entire project was written with the heavy use of Claude Code
It works well for me on MacOS and Debian Linux, it should work
on Windows, but I haven't tested it.

Expect plenty of weird behavior, I haven't finished user testing yet.
For example, I initially conceived of this as 0800-2000, because we all
need some unstructured time. As a result, you absolutely cannot put a
task  on the timeline after 2000, despite the timeline being a full
24hr.

## It sucks on mobile because it's heavily dependant on keyboard controls.

![A screenshot of ADHD Assistant](/screenshots/ADHD_Assistant.png?raw=true "ADHD Assistant")

A local-first single-user webpage for taming the day. Day-timeline +
tasks tab + quick-capture inbox, all stored as JSON files next to the
server. Nothing leaves your machine — no accounts, no cloud, no sync.

Currently "single user" as there's just one data directory.  I guess you 
could spin up another server on a different port in a different folder 
for a different user if you enjoy misery. 

It runs on http on localhost by default, you can change it by editing server.py.
You can even add a cert and run https if you like, but why?


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

## Keyboard shortcuts

- `\t` — capture a task (slash-command modal)
- `\n` — capture an inbox note
- `\f` — start a focus timer
- `c` — toggle done on the selected task
- `w` / `s` — nudge selected task earlier / later
- `a` / `d` — increase / decrease selected task priority (low/medium/high)
- `r` / `e` — read / edit selected task's notes

## General functionality
This was meant for the adhd brain, you can schedule things today, or...not today.

You get a counter for tasks completed, a star for completing high priority tasks.

You can add notes, and tasks, and notes to tasks, make tasks from notes.

For tasks you want repeat, like whatever, exercise, music practice, staring into the void,
you can mark them as repeating.  You get credit for completing them but they will still be
there tomorrow to do again. Sisyphus would be proud.

For the things you know you're not going to get to, you can snooze them for a period of 
time and they will go into a snoozed task section.  
  
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
