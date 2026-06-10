# ADHD assistant

## IMPORTANT!  run.bat is UNTESTED, use at your own risk.
This entire project was written with the heavy use of Claude Code
It works well for me on MacOS and Debian Linux, it should work
on Windows, but I haven't tested it.

Expect plenty of weird behavior, I haven't finished user testing yet.
I initially conceived of this as 0800-2000, because we all need some
unstructured time. That window is now just a visual cue — the timeline
is a full 24hr and you can drop a task at any hour; anything outside
0800-2000 just renders dimmed so putting it there feels deliberate.

## Mobile works now (it didn't used to)

It's still keyboard-happy on desktop, but on a phone you get a
Timeline/Triage tab switcher plus touch controls — an inline inbox
capture bar, a + task bar, and a one-task-at-a-time Queue — so you can
actually use it without a keyboard.

![A screenshot of ADHD Assistant](/screenshots/ADHD_Assistant.png?raw=true "ADHD Assistant")

![ADHD Assistant on mobile](/screenshots/ADHD_Assistant_mobile.png?raw=true "ADHD Assistant on mobile")

A local-first single-user webpage for taming the day. Day-timeline +
tasks tab + quick-capture inbox, all stored as JSON files next to the
server. Nothing leaves your machine — no accounts, no cloud, no sync.

Currently "single user" as there's just one data directory.  I guess you 
could spin up another server on a different port in a different folder 
for a different user if you enjoy misery. 

It runs on http on localhost by default, you can change it by editing server.py.
You can even add a cert and run https if you like, but why?

If you do serve it beyond localhost, note the server now rejects unknown Host
headers (a DNS-rebinding guard). localhost and Tailscale (`*.ts.net`) work out
of the box; for anything else set `ADHD_ALLOWED_HOSTS=myhostname,192.168.1.50`
before launching. If you get a `400 Invalid host header`, that's this.
The recommended way to reach it from other devices is `tailscale serve` —
the app stays bound to localhost and you get https for free.


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
- `\q` — work one task at a time (focus queue)
- `c` — toggle done on the selected task
- `w` / `s` — nudge selected task earlier / later
- `a` / `d` — increase / decrease selected task priority (low/medium/high)
- `l` / `m` — less / more time (size the selected task in 5-min steps)
- `r` / `e` — read / edit selected task's notes

## General functionality
This was meant for the adhd brain, you can schedule things today, or...not today.

You get a counter for tasks completed, a star for completing high priority tasks.

There's also a momentum gauge — a little flame that warms up the more you use the
app and cools off *gently* if you don't. Falling off for a day doesn't nuke your
progress the way a streak would; it just dims a bit. Click it for a gauge + a
heatmap of the last couple months.

You can add notes, and tasks, and notes to tasks, make tasks from notes.

For tasks you want repeat, like whatever, exercise, music practice, staring into the void,
you can mark them as repeating.  You get credit for completing them but they will still be
there tomorrow to do again. Sisyphus would be proud.

Repeating tasks can have a set time (they land on the timeline) or no set time at all —
those just show up in the Queue on the days you picked, no clock involved.

The Queue is where the un-timed stuff lives: anything you haven't dropped on the timeline.
It hands you one card at a time so you're not staring at a list. Give a task a size with
`l` / `m` (less / more time, 5-minute steps) so a five-minute thing and a two-hour thing
don't look the same.

Start a focus timer and, if something's scheduled for right now, it rides along on the
timer screen so you can finish it or snooze it without leaving.

For the things you know you're not going to get to, you can snooze them for a period of 
time and they will go into a snoozed task section.  
  
## Backup

Everything is `data/`. Copy the folder, you've got a backup. Replace it
to restore.

## Manual setup (if `run.sh` isn't your thing)

```sh
uv run python server.py     # auto-syncs deps from pyproject.toml + uv.lock
```

## Development

Tests use pytest + pytest-playwright. `uv sync` brings in the dev
group from `pyproject.toml`:
```sh
uv sync             # runtime + dev deps
uv run playwright install chromium
make test           # unit + server tests
make test-e2e       # browser tests (slower)
make test-all       # everything
```
