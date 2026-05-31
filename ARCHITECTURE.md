# Architecture

*Last updated: 2026-05-29 — mobile tabbed shell (#20) + focus queue (#21) shipped, plus recur/snooze popover clipping fix. See also [README.md](README.md).*

## One-paragraph summary

A single Python FastAPI process serves a plain-HTML/ES-modules SPA on `http://localhost:1440`. All persistent state lives in versioned JSON files under `data/`. **Tasks** are the single source of truth — the day timeline is a *derived view* of tasks whose `schedule.date` matches the selected day, and the snoozed/done/recurring states are derived from per-task timestamps. Every mutation is a `PATCH /api/tasks/{id}` (or `POST`/`DELETE`); the server keeps no in-memory state between requests. Renderers subscribe to a tiny in-process event bus (`web/events.js`); mutators emit and only the interested subscribers redraw.

## Tech stack

- **Server:** Python ≥ 3.11, FastAPI ≥ 0.115, Uvicorn, Pydantic v2. Three files: `server.py`, `storage.py`, `calendar_overlay.py`.
- **Frontend:** Plain HTML + CSS + ES2020 modules. No bundler, no framework, no build step. 20 modules in `web/`, ~4,300 lines total.
- **Storage:** Versioned JSON files in `data/` (gitignored). Atomic writes via `tempfile` + `os.replace`. Schema upgrades are chained on read.
- **Calendar overlay:** Reads `.ics` files under `data/UserCalendar/` via `icalendar` + `recurring-ical-events`. Strictly one-way — the assistant never writes back.
- **Package manager:** [uv](https://docs.astral.sh/uv/) (project-managed via `pyproject.toml` + `uv.lock`). `uv run python server.py` materialises `.venv` from the lockfile on first run.
- **Port:** `1440` (minutes in a day — thematic).

## Repository layout

```
.
├── server.py              # FastAPI app + Pydantic models + lifespan migration
├── storage.py             # JSON I/O, ID generation, schema versioning, migrate_days
├── calendar_overlay.py    # .ics → flat event dicts, with (path, mtime) cache
├── pyproject.toml         # [project] runtime deps + [dependency-groups] dev
├── uv.lock                # locked dep tree (committed)
├── run.sh / run.bat       # bootstrap: check uv, exec `uv run python server.py`
├── make_release.sh        # produces dist/adhd-assistant-YYYYMMDD.tar.gz
├── Makefile               # test, test-all, test-e2e, test-watch, run
├── pytest.ini             # markers: unit, e2e (strict)
├── README.md              # recipient-facing
├── ARCHITECTURE.md        # this file
├── CONTEXT.md             # the user’s ADHD shape and what the app exists to do
├── TODO.md                # roadmap + checklist; *why* lives here
├── web/
│   ├── index.html         # topbar + timeline + triage panel + modals
│   ├── styles.css         # dark theme; CSS custom properties for colors
│   ├── main.js            # boot orchestrator: wires every init*, fires fetches
│   ├── dom.js             # one `document.querySelector` per element, exported
│   ├── events.js          # tiny pub-sub bus + EVENTS vocabulary constants
│   ├── state.js           # canonical `tasks[]` + derived `dayTasks[]` + helpers
│   ├── api.js             # thin fetch wrappers; no state, no rendering
│   ├── time.js            # constants, formatters, free-slot search, presets
│   ├── timeline.js        # day timeline rendering + drag/resize, calendar overlay positioning
│   ├── triage.js          # Tasks + Inbox tabs, row rendering, snooze + recur popovers
│   ├── modal.js           # \-prefixed slash-command capture modal
│   ├── keyboard.js        # global keydown router (slash, WASD, c, r/e, \q, etc.)
│   ├── markdown.js        # sanitising MD→HTML renderer + plaintext preview
│   ├── notes.js           # notes *editor* modal
│   ├── notes-read.js      # notes *reader* modal
│   ├── focus.js           # focus timer state machine + launcher
│   ├── queue.js           # focus queue: one-task-at-a-time overlay (today-scoped)
│   ├── views.js           # mobile top-level Timeline/Triage view switcher
│   ├── wins.js            # ✓ N today counter + priority stars
│   ├── calendar.js        # /api/calendar/events fetch + overlay render
│   └── toast.js           # transient + undo toasts
├── data/                  # created on first run; gitignored
│   ├── tasks.json         # versioned: {"version": 3, "items": [...]}
│   ├── inbox.json         # versioned: {"version": 3, "items": [...]}
│   ├── UserCalendar/      # drop-zone for read-only .ics files
│   └── days/              # legacy per-day files (only on pre-Phase-4 installs)
└── tests/
    ├── conftest.py        # tmp_data_dir, client, factory fixtures
    ├── unit/              # 161 tests via FastAPI TestClient (< 2 s)
    └── e2e/               # 137 tests via pytest-playwright + uvicorn subprocess
```

## Data model

### Task (`data/tasks.json` → `items[]`, schema version 3)

```jsonc
{
  "id": "kl7ZKi9JWk4",               // 8-12 chars, secrets.token_urlsafe
  "title": "Read deep agents docs",
  "priority": "medium",              // "low" | "medium" | "high"
  "notes": "Started Tuesday\n\nhttps://docs.example.com/…",  // Markdown
  "schedule": {                      // null when unscheduled
    "date": "2026-05-21",
    "startMin": 540,
    "durationMin": 30
  },
  "done": false,
  "tags": [],
  "defaultDurationMin": 30,          // last-used schedule duration; used by auto-schedule
  "dueDate": "2026-05-23",           // YYYY-MM-DD or null — display only in v1
  "recurring": false,                // true: stays after `done`, resets at local midnight
  "recurSchedule": null,             // v3: {startMin, durationMin, days[]} sticky-time spec; projected onto matching days
  "recurExceptions": [],             // v3: ["YYYY-MM-DD"] days the sticky projection is suppressed
  "snoozedUntil": null,              // epoch seconds or null; >now hides from main list
  "createdAt": 1779190000.0,
  "updatedAt": 1779200000.0,
  "completedAt": null,               // epoch seconds; refreshed each cycle for recurring
  "deletedAt": null                  // epoch seconds; soft-delete sentinel
}
```

Schema version 2 dropped the v1 `status: "active" | "not_today"` field in favor of `snoozedUntil` (a richer "come back later" mechanism). Legacy rows on disk are silently stripped of the `status` key by the v1→v2 upgrade. Version 3 added the sticky-time `recurSchedule` + `recurExceptions` pair (Tier 2 #15) for tasks that re-project onto the timeline at a fixed time on configured days.

### Inbox item (`data/inbox.json` → `items[]`)

```jsonc
{
  "id": "5rgS8krvLeI",
  "text": "check this out https://example.com/article",
  "url":  "https://example.com/article",   // detected from leading http(s)
  "title": null,                            // populated by future URL-fetch
  "createdAt": 1779190000.0,
  "deletedAt": null
}
```

### Calendar event (response-only, never stored)

```jsonc
{
  "summary": "Standup",
  "startMin": 540,           // minutes from local midnight
  "endMin": 570,
  "allDay": false,
  "source": "work.ics"       // filename relative to data/UserCalendar/
}
```

## HTTP API

| Method | Path                              | Purpose                                                                          |
|--------|-----------------------------------|----------------------------------------------------------------------------------|
| GET    | `/`                               | Serves `web/index.html`                                                          |
| (mount)| `/web/*`                          | Static files with `Cache-Control: no-store` (so ES-module edits land on reload)  |
| GET    | `/api/tasks`                      | All live tasks, newest-first                                                     |
| POST   | `/api/tasks`                      | Create. Body may include `schedule` to create-and-schedule.                      |
| PATCH  | `/api/tasks/{id}`                 | Partial update. `model_fields_set` distinguishes "don't change" from "set null". |
| DELETE | `/api/tasks/{id}`                 | Soft-delete (sets `deletedAt`). Hidden from lists; restorable.                   |
| POST   | `/api/tasks/{id}/restore`         | Clear `deletedAt`. Powers the Undo toast.                                        |
| GET    | `/api/day/{date}`                 | Derived view: live tasks where `schedule.date == date`.                          |
| GET    | `/api/inbox`                      | All live inbox items, newest-first                                               |
| POST   | `/api/inbox`                      | Add from raw text. Server detects a leading http(s) URL.                         |
| DELETE | `/api/inbox/{id}`                 | Soft-delete                                                                      |
| POST   | `/api/inbox/{id}/restore`         | Clear `deletedAt`                                                                |
| GET    | `/api/calendar/events?date=…`     | Read-only overlay for the given date from `data/UserCalendar/*.ics`              |

Validation: empty titles → 400, unknown priority → 400, malformed `YYYY-MM-DD` → 400, missing id → 404. Pydantic models reject unknown fields silently (`model_fields_set` only contains what the client sent).

### Done / recurring semantics

A `PATCH {done: true}` against a task stamps `completedAt = now`. For **recurring** tasks the server refreshes `completedAt` on *every* `done: true` PATCH, even when `done` was already true, so the wins counter picks up each daily cycle. Going `done: true → false` clears `completedAt`. Non-recurring tasks only stamp on the rising edge — they're idempotent.

Client-side `isDoneToday(task)` derives the on-screen check state: for non-recurring tasks the raw flag is canonical; for recurring tasks the check shows only if `completedAt` falls within the local day. Yesterday's check → undone glyph; clicking re-checks it and bumps the wins counter.

### Snooze semantics

A `snoozedUntil` greater than `Date.now()` hides the task from the main Tasks list and slots it into a collapsible `Snoozed (N)` disclosure at the bottom. The client-side filter `isSnoozedNow(task)` runs in `renderTasksList`. When the time passes the task reappears automatically on the next render (no notification, no daemon).

If the snoozed task was scheduled on today's timeline at the moment of snooze, the same PATCH also clears `schedule` — the slot is reclaimable for something else. Future-day schedules are left alone (per current design — see TODO).

## Storage versioning

Files on disk are wrapped: `{"version": N, "items": [...]}`. `storage.py` defines `CURRENT_VERSION = 3` and a chain of `_upgrade_vN_to_vN+1` functions. `load_versioned(path)` runs any missing upgrades on read, persists the upgraded shape, and returns it. `save_versioned(path, data)` always stamps the current version.

Current upgrade chain:

- **v0 → v1** (`_upgrade_v0_to_v1`): pre-A3 files had no version key. The upgrade adds `version: 1` without touching items.
- **v1 → v2** (`_upgrade_v1_to_v2`): strips the deprecated `status` key from every item.
- **v2 → v3** (`_upgrade_v2_to_v3`): initialises `recurSchedule: null` and `recurExceptions: []` on every item (idempotent).

Additionally, on every load `server._normalize_task(item)` lazy-fills schema fields that earlier records didn't have (`updatedAt`, `completedAt`, `tags`, `defaultDurationMin`, `dueDate`, `recurring`, `recurSchedule`, `recurExceptions`, `snoozedUntil`). This is the same code path whether reading a fresh file or migrating an old one.

### One-shot legacy fold

`migrate_days(days_dir, tasks_file, *, now)` reads any leftover `data/days/YYYY-MM-DD.json` files from the pre-Phase-4 era, folds their tasks into `tasks.json` (matching by id, filling gaps without overwriting), and renames the source files to `*.json.migrated` so subsequent boots skip them. The function is a top-level pure function so it's unit-testable without booting the server, and returns a `{renamed, added, updated}` summary. New installs never create `data/days/`; the migration is a no-op if the directory is absent.

## Frontend architecture

### Module shape

`web/main.js` is the entry point — every other module exports an `init*` function and main.js calls them in a fixed order. After init, mutations flow exclusively through the event bus (`web/events.js`):

```
state.js mutators ── emit ──▶  bus  ──▶  subscribed renderers
   (upsertTaskLocal, removeTaskLocal,
    setTasks, setCurrentDate)
```

`EVENTS` vocabulary (frozen): `TASK_CREATED`, `TASK_CHANGED`, `TASK_DELETED`, `TASK_COMPLETED`, `INBOX_CREATED`, `INBOX_DELETED`, `DAY_CHANGED`.

Subscribers as of today:

| Subscriber               | Events it listens to                              | What it redraws                          |
|--------------------------|---------------------------------------------------|------------------------------------------|
| `timeline.js#renderTasks`| `TASK_*`, `DAY_CHANGED`                           | Day-timeline blocks                      |
| `timeline.js#scrollToFocus` | `DAY_CHANGED`                                  | Auto-scroll to 07:30 on day switch       |
| `triage.js#renderTasksList` | `TASK_*`, `DAY_CHANGED`                        | Tasks tab + snoozed disclosure           |
| `wins.js`                | `TASK_CHANGED`, `TASK_COMPLETED`, `TASK_DELETED`, `DAY_CHANGED` | Wins counter + stars       |
| `calendar.js`            | `DAY_CHANGED`                                     | Calendar overlay                         |

This means `setSelectedTask` doesn't trigger a re-render — selection only flips a `.selected` class via `state.js#refreshSelectionDom`.

### Client state (live bindings)

```js
// state.js — exported with `let`, so importers see mutations as live bindings.
let tasks = [];          // canonical, from /api/tasks
let dayTasks = [];       // derived: tasks where schedule.date === currentDate
let currentDate = "…";   // YYYY-MM-DD
let selectedTaskId = null;
```

`recomputeDayView()` rebuilds `dayTasks` whenever `tasks` or `currentDate` change, *before* the corresponding bus emit, so subscribers see consistent state.

### Task row layout (Tasks tab)

The Tasks-tab uses a reserved-slot CSS grid so indicators land in the same column on every row:

```
[stripe] [arrow] [title] [↻] [📝] [due] [💤] [actions]
```

- **arrow** — wide left-edge bar. `data-state="unscheduled"` shows `‹`; `data-state="scheduled"` shows `›`. Click toggles schedule on/off today's timeline.
- **↻** — recurring toggle. Always renders the glyph; `data-recurring="true|false"` drives bright-vs-muted styling. Click PATCHes `recurring`.
- **📝** — opens the notes reader (or empty slot).
- **due** — renders only when `dueDate` is set; class is one of `due-overdue` / `due-today` / `due-soon` / `due-future`.
- **💤** — opens a 5-preset snooze popover (1h / EOD / tomorrow morning / 3d / 1w).
- **actions** — bordered vertical bar mirroring `.ti-arrow` on the left. Top 2/3 is done-toggle (muted ✓ → green ✓ when active); bottom 1/3 is delete (muted × → red × on hover).

Snoozed tasks render in a separate `.ti-actions`-less view inside the `Snoozed (N)` disclosure; the snooze button there is replaced by a *Wake now* button.

### Timeline

Two-constant day model (`time.js`):

- `TIMELINE_START_MIN = 0`, `TIMELINE_END_MIN = 1440` — the timeline renders the full 24h.
- `DAY_START_MIN = 480` (08:00), `DAY_END_MIN = 1200` (20:00) — the auto-schedule and free-slot search bound. New tasks land inside this window; the user can drag outside it.

The day pane is scrollable; `scrollToFocus` lands at 07:30 on every day switch so the focus window is visible without scrolling.

`findFreeSlotIn(others, desiredStart, duration)` is shared by drag-release ("snap past obstacles"), W/S nudges ("skip past obstacles"), and auto-schedule. It returns the nearest non-overlapping `startMin` or `null` when the window is exhausted.

### Calendar overlay

`calendar_overlay.events_for_date(date_str, calendar_dir)`:

1. For each `*.ics` file under `data/UserCalendar/`, parse it (cached by `(path, mtime)` so unchanged files cost nothing on re-fetch).
2. Use `recurring-ical-events` to expand RRULEs/EXDATEs within `[local midnight, +24h)`.
3. Project each event to `{summary, startMin, endMin, allDay, source}` in local-day minutes.

The endpoint accepts a date and returns a flat list. `calendar.js` subscribes to `DAY_CHANGED`, fetches the events for the new date, and renders them as translucent backdrop blocks on the timeline. The overlay never tracks selection, never PATCHes anything — it's read-only.

### Mobile view switcher

`web/views.js` adds a top-level Timeline / Triage switcher for narrow viewports. The collapse is CSS-driven (`@media (max-width: 720px)`): the two-column `.layout` grid becomes a single column, and `body[data-mobile-view="timeline" | "triage"]` hides the inactive panel. `switchAppView(name)` sets that attribute, toggles `.app-view.active`, and persists to `localStorage["app-view"]`; `initAppViews()` restores the saved view on boot. Above 720 px the switcher is `display: none` and both panels render side-by-side — desktop is untouched. The switcher mirrors the in-triage `switchTab` pattern but operates one level up (whole panels, not tabs within the triage column).

### Focus queue

`web/queue.js` is a full-screen overlay (`#queue-overlay`, modeled on the focus-timer overlay, z-index 100) that presents today's actionable tasks one at a time. It holds no bus subscription — the queue is built fresh from `tasks` each time it opens, so it always reflects current state without needing live updates. State machine: `idle | running | empty`.

- **Scope = today only.** `isTodayRelevant(task)` excludes `isSnoozedNow` / `isDoneToday`, and includes a task with a real-or-projected today schedule (`projectedScheduleFor` covers sticky recurring) **or** `dueDate <= todayKey()` (due-today + overdue). `buildQueue()` sorts timed-first by `startMin`, then untimed by overdue-first then priority, and returns an array of task ids; `queue[0]` is the current card.
- **Complete** PATCHes `{done: true}` through the canonical `patchTaskRecord` → `upsertTaskLocal` path, drops the head, and advances; draining shows the **All clear** empty state.
- **Skip** rotates the head to the back (`queue.push(queue.shift())`) — nothing is lost, the count holds, you cycle.
- Entry: a `Queue` button in `.timeline-actions` and the `\q` slash command. While active (`isQueueActive()` gate in `keyboard.js`): `c`/`Enter` complete, `s` skip, `Esc` exits. No server change — pure client feature over existing selectors and endpoints.

## Operational notes

- **Run:** `./run.sh` (or `make run` for the same thing inline). First launch fetches Python 3.11 via uv if not installed, materialises `.venv` from `uv.lock`, then starts the server and opens the browser.
- **Use uv, never pip directly:** `uv sync` for dev (pulls runtime + dev deps); `uv run --no-dev …` for production-shape runs.
- **Tests:** `make test` (161 unit, < 2 s). `make test-e2e` (137 E2E, ~150 s on Chromium). `make test-all` for both.
- **First-time E2E setup:** `uv run playwright install chromium` (one-shot ~90 MB download).
- **Smoke testing the server by hand:** use a throwaway date like `1999-01-01` for any `PATCH` writes — never today, never a real date with user data.
- **Stale bytecode:** if a server change "doesn't take effect," `rm -rf __pycache__` and rerun. (See memory note: `feedback_clear_pycache.md`.)
- **Stale browser modules:** `/web/*` is served with `Cache-Control: no-store`, so a regular reload is enough — no Cmd-Shift-R needed.
- **Sharing the app:** `./make_release.sh` produces a ~115 KB tarball with `pyproject.toml` + `uv.lock` + source + `run.sh`. Recipient needs only uv. See README.md.
- **Per-machine data:** the `ADHD_DATA_DIR` env var redirects the data root. E2E tests use it to isolate each subprocess.

## Testing

Three layers, sharply different in cost and value:

| Layer | Tool | Lives in | Run | What it catches |
|---|---|---|---|---|
| **Server unit / integration** | `pytest` + FastAPI `TestClient` | `tests/unit/` (161 tests) | `make test` | Endpoint contracts, validation, persistence, migration chain, calendar parsing |
| **End-to-end happy paths** | `pytest-playwright` | `tests/e2e/` (137 tests) | `make test-e2e` | Drag/resize, modals, slash-commands, layout (incl. mobile view switcher), task-row interactions, focus timer, focus queue, calendar overlay |
| **Smoke (dev-time)** | `curl` + Claude Preview MCP | n/a | ad-hoc | Quick verification while iterating; not committed |

**Isolation:**

- **Unit:** `tmp_data_dir` monkeypatches `server.DATA`, `server.DAYS_DIR`, `server.INBOX_FILE`, `server.TASKS_FILE`, `server.CALENDAR_DIR` to a per-test temp directory. The `client` fixture wraps `TestClient(server.app)` and enters its context manager so the lifespan runs against the patched paths.
- **E2E:** `live_server` spawns `uvicorn server:app` on a random free port with `ADHD_DATA_DIR=<temp>` in the environment. Each test gets its own subprocess and data dir; teardown terminates the process. Real user data in `<repo>/data/` is never touched.

**Known wall-clock flake:** five tests that schedule on today's timeline call `findFreeSlot` against the 08:00–20:00 window. After ~19:45 local there's no free slot left and the tests fail. The fix is to use a stable far-future date (e.g. `2099-06-15`) in those tests; tracked in TODO.

**Deliberately out of scope:**

- CI integration — local-only project.
- Frontend unit tests — pure DOM logic; cost > value without a bundler. E2E covers it.
- Visual screenshot diffing — high-maintenance for our scale.
- Time-of-day precision tests — assert ranges or regex patterns, never exact minutes.

## Design decisions and reasoning

| Decision                                       | Why                                                                                                       |
|------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| **Tasks as single source of truth**            | Pre-Phase-4 per-day files duplicated state and made "Tasks tab shows everything" awkward. One store is simpler. |
| **Day view derived, not stored**               | Eliminates sync bugs between day file and tasks store.                                                    |
| **`PATCH` per task, not `PUT` whole-day**      | Atomic per-task changes. No "save the whole day" semantics that could overwrite concurrent edits.         |
| **`model_fields_set` in PATCH**                | Lets clients distinguish "don't change" from "set to null" — needed to unschedule via `schedule: null` and to clear `snoozedUntil`. |
| **Soft-delete via `deletedAt`**                | One-click destructive deletion is wrong for ADHD. Records stay with `deletedAt` set; lists filter them out; an Undo toast restores via `POST /restore`. |
| **Schema versioning via `_upgrade_vN_to_vN+1`**| Future migrations are a single function added to the chain. Beats hard-coded one-shot scripts. |
| **`_normalize_task` lazy-fills new fields**    | Old rows read into memory get the new field defaults without rewriting the file. Cheap to add a field. |
| **Recurring done refreshes `completedAt` per PATCH** | Wins counter keys off `completedAt within today`. A daily cycle has to look like a new completion to bump the counter. |
| **Snooze hides via client-side filter**        | No daemon needed; the task reappears on the next render after `snoozedUntil` passes. Server doesn't care about wall clock. |
| **Calendar overlay one-way only**              | Writing back is a sync problem with no winning answer for a single-user local app. Non-goal, not deferred. |
| **Backslash slash-commands (`\n`, `\t`, `\f`)**| `/` triggers browser Quick Find — `preventDefault` can't suppress it reliably in Firefox/some Chromes. `\` has no browser meaning. |
| **WASD on a selected task**                    | Gaming-style mental model: W/S nudge time, A/D adjust priority. Single-modifier, no chording.            |
| **× on day block = unschedule, not delete**    | Tasks always exist in the Tasks tab; removing from the timeline shouldn't destroy the task.              |
| **× on Tasks-tab row = delete (soft)**         | Tasks tab is the "canonical list". Delete is the destructive op there; Undo toast cushions misclicks.    |
| **Done + delete in one right-edge bar**        | Mirrors the arrow bar on the left. Done is 2/3 height, delete 1/3 — visual hierarchy + a soft misclick guard. |
| **Atomic writes via tempfile + `os.replace`**  | Prevents partial-write corruption if the process crashes mid-save.                                        |
| **`Cache-Control: no-store` on `/web/*`**      | ES modules cache aggressively by default. Single-user dev loop is more painful than the bandwidth save.   |
| **Topbar `position: fixed`**                   | With horizontal-scroll layout on narrow viewports, the clock would otherwise scroll off-screen.           |
| **Default tab: Tasks**                         | Empty inbox + tasks-only data was the common case; defaulting to inbox made the app look empty.           |
| **JSON files, not SQLite**                     | Human-readable, git-friendly, single-file backup. SQLite is overkill at this scale.                       |
| **No framework / bundler**                     | Friction to modify is the lowest possible. Anyone can read the source. No tooling rot.                    |
| **uv project (pyproject.toml + uv.lock)**      | Locked dep tree ships with the release tarball; recipients get the exact resolution. `uv run` is one command end-to-end. |

## Significant refactors

History of shape-changing events. Things that aren't obvious from the current code and would surprise an archaeologist reading `git blame`.

- **2026-05-19 — Per-day files retired (Phase 4).** Tasks moved from `data/days/YYYY-MM-DD.json` (whole-day `PUT`) into a single `tasks.json` with optional `schedule`. `migrate_days()` runs on startup, folds any leftover day-files, and renames them to `*.json.migrated`. New installs never create `data/days/`.
- **2026-05-19 — Capture box removed, slash-commands added.** The Inbox panel used to have an always-visible textbox. Removed in favor of `\n` / `\t` popups. Prefix moved from `/` to `\` because browsers intercept `/`.
- **2026-05-20 — Phase 4.7 schema + safety.** Soft-delete via `deletedAt`; `updatedAt` + `completedAt`; file-wrapper `{"version", "items"}` + chained upgrades; server-only IDs; `tags: string[]` placeholder.
- **2026-05-20 — Phase 4.8 modules + event bus.** `app.js` (~1500 lines) split into 18 ES modules under `web/`. `applyTasks()` retired in favor of a pub-sub bus (`events.js`). Renderers subscribe to the slice they care about. `storage.py` extracted from `server.py`.
- **2026-05-20 — Phase 4.9 Markdown notes + editor.** Notes are now Markdown (sanitised client-side via `markdown.js`). Split into a reader modal (`notes-read.js`, opened by 📝) and an editor modal (`notes.js`, opened by `e` or the reader's edit button).
- **2026-05-20 — Tier 2 #5 + Phase 7: 24h day + calendar overlay.** Timeline now spans 0–1440 (was 7am–9pm). Auto-schedule still bounded to 08:00–20:00. `calendar_overlay.py` + `/api/calendar/events` + `web/calendar.js` render `.ics` events as a translucent backdrop.
- **2026-05-20 — Tier 2 #9: focus timer.** Self-contained countdown with launcher modal, running overlay, done state. Driven by `\f` or a topbar button.
- **2026-05-20 — Tier 2 #7 + #11: wins counter + priority stars + topbar layout.** Wins counter (`wins.js`) shows `✓ N today`; one ⭐ per high-priority completion, wrapping 5 per row with `+N` overflow at 15. Focus button centered over the timeline; stars sit beside the wins count.
- **2026-05-21 — Tier 2 #12: task row redesign + schema v2.** Reserved-slot CSS grid replaces the variable meta-row. Dropped `status`; added `dueDate`, `recurring`, `snoozedUntil`. Arrow bar replaces the Today/Off-today buttons; snooze popover replaces "Later"; recurring `↻` toggle stays visible after done and resets at local midnight; due-date display by urgency; right-edge action bar (done 2/3, delete 1/3) mirrors the arrow.
- **2026-05-21 — Packaging.** Added `README.md`, `run.sh` / `run.bat`, `make_release.sh`. Converted to a uv-managed project: `pyproject.toml` + `uv.lock` supersede `requirements.txt` / `requirements-dev.txt`. Release tarball ships locked dep tree.
- **2026-05-29 — Tier 2 #15: sticky-time recurring (schema v3).** Added `recurSchedule` + `recurExceptions`. The day view projects a block at the configured time on matching weekdays without writing to disk (`projectedScheduleFor`); editing/dragging a projection writes a real `schedule` for that day. `↻` recur popover replaces the boolean toggle; projected blocks render dashed.
- **2026-05-29 — Tier 2 #20 + #21: mobile shell + focus queue (no server change).** `web/views.js` adds a CSS-collapse Timeline/Triage view switcher below 720 px (desktop untouched). `web/queue.js` adds a one-task-at-a-time overlay scoped to today (Complete / Skip-to-back), built fresh from `tasks` on open rather than subscribing to the bus. Same change fixed recur/snooze popover clipping via a shared `positionPopover` helper (prefer-below, flip-above, clamp) plus a `max-height`/`overflow-y` safety net on `.snooze-menu` / `.recur-menu`.

## Planned changes

Status of each is tracked in TODO.md; the *why* lives there too. Notable items still open:

- **Empty-state CTAs + section counts (Tier 2 #10)** — "Press `\n` to capture" inside empty tabs; Tasks-tab + Snoozed counts.
- **Push-forward on uncompleted scheduled tasks (Tier 2 #16)** — per-task opt-in "drift" that re-anchors a block past the now-line if it's not done.
- **Tier 3** — micro-celebration on done, in-page search (`\?`), URL title fetch for inbox, settings menu (incl. configurable focus window), periodic purge of long-soft-deleted records.
- **Parked** — picture attachments via Markdown image refs, recurring custom cadences, calendar v2 with auto-refresh on file change.

Recently shipped (now history above, not planned): Phase 5 polish (#6), stats modal (#8), focus timer (#9), task-row redesign + schema v2 (#12), sticky-time recurring + schema v3 (#15), off-hours visual pressure (#19), mobile tabbed shell (#20), focus queue (#21).
