"""Local ADHD assistant server.

Run: python server.py
Then open http://localhost:1440
"""

from __future__ import annotations

import datetime as _dt
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

# Storage primitives live in storage.py. They're imported here (not re-imported
# at call sites) so tests can monkeypatch ``server.DATA`` etc. and have route
# handlers pick up the override via this module's globals.
from storage import (
    ACTIVITY_FILE,
    CALENDAR_DIR,
    CURRENT_VERSION,
    DATA,
    DATE_RE,
    DAYS_DIR,
    INBOX_FILE,
    ROOT,
    TASKS_FILE,
    load_versioned,
    migrate_days,
    new_id,
    read_json,
    save_versioned,
    write_json,
)
import calendar_overlay

WEB = ROOT / "web"

PORT = 1440
TASK_PRIORITIES = ("low", "medium", "high")
# Tier 2 #12 dropped the active/not_today status in favor of snoozedUntil.
# Legacy items with `status` get the key stripped during the v1→v2 upgrade.


def ensure_data() -> None:
    DATA.mkdir(exist_ok=True)
    # data/UserCalendar/ is the drop-point for read-only .ics overlays.
    # Created up-front so users know where calendar exports go even
    # before they've added one.
    CALENDAR_DIR.mkdir(exist_ok=True)
    if not INBOX_FILE.exists():
        save_versioned(INBOX_FILE, {"items": []})
    if not TASKS_FILE.exists():
        save_versioned(TASKS_FILE, {"items": []})
    # Activity log powering the momentum gauge — own simple shape, not part of
    # the versioned task/inbox schema chain.
    if not ACTIVITY_FILE.exists():
        write_json(ACTIVITY_FILE, {"version": 1, "days": {}})
    # Upgrade any pre-A3 files on startup so subsequent reads see the
    # current schema shape.
    load_versioned(INBOX_FILE)
    load_versioned(TASKS_FILE)
    # data/days/ is the legacy per-day storage shape from before Phase 4;
    # if it exists on this install, fold its contents into tasks.json
    # (one-shot, idempotent — files get renamed .migrated on success).
    # If the dir doesn't exist (e.g. fresh install), migrate_days returns
    # an empty summary without creating anything.
    migrate_days(DAYS_DIR, TASKS_FILE, now=time.time())


def _is_live(item: dict) -> bool:
    return item.get("deletedAt") is None


def _normalize_task(item: dict) -> dict:
    """Lazy-fill schema fields on records read from disk.

    Mutates the dict in place and returns it. Pre-A2 rows lack
    ``updatedAt`` / ``completedAt``, pre-A5 rows lack ``tags``, pre-A6 rows
    lack ``defaultDurationMin``, pre-Tier-2-#12 rows lack ``dueDate`` /
    ``recurring`` / ``snoozedUntil`` and may still carry the now-deprecated
    ``status`` key (which we silently drop). For ``defaultDurationMin`` we
    prefer the existing schedule's ``durationMin`` when present so
    re-scheduling a previously-scheduled task picks up its last known
    duration.
    """
    if "updatedAt" not in item:
        item["updatedAt"] = item.get("createdAt", 0.0)
    if "completedAt" not in item:
        item["completedAt"] = None
    if "tags" not in item:
        item["tags"] = []
    if "defaultDurationMin" not in item:
        sched = item.get("schedule") or {}
        item["defaultDurationMin"] = int(
            sched.get("durationMin", DEFAULT_DURATION_MIN)
        )
    if "dueDate" not in item:
        item["dueDate"] = None
    if "recurring" not in item:
        item["recurring"] = False
    if "snoozedUntil" not in item:
        item["snoozedUntil"] = None
    # Tier 2 #15 sticky-time recurrence.
    if "recurSchedule" not in item:
        item["recurSchedule"] = None
    if "recurExceptions" not in item:
        item["recurExceptions"] = []
    # Silently strip the legacy active/not_today status field. Pre-v2 files
    # may still have it on disk; ``_upgrade_v1_to_v2`` clears it on the next
    # versioned read, but in-flight dicts (e.g., during migrate_days) might
    # still carry it.
    item.pop("status", None)
    return item


class CaptureIn(BaseModel):
    text: str


class InboxItem(BaseModel):
    id: str
    text: str
    url: Optional[str] = None
    title: Optional[str] = None
    createdAt: float
    deletedAt: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data()
    yield


app = FastAPI(title="ADHD assistant", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/api/inbox")
def get_inbox() -> dict:
    data = load_versioned(INBOX_FILE)
    live = [i for i in data.get("items", []) if _is_live(i)]
    items = sorted(live, key=lambda i: i["createdAt"], reverse=True)
    return {"items": items}


@app.post("/api/inbox", response_model=InboxItem)
def post_inbox(payload: CaptureIn) -> InboxItem:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty capture")

    url: Optional[str] = None
    lowered = text.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        url = text.split()[0]

    item = InboxItem(
        id=new_id(),
        text=text,
        url=url,
        title=None,
        createdAt=time.time(),
    )
    data = load_versioned(INBOX_FILE)
    data.setdefault("items", []).append(item.model_dump())
    save_versioned(INBOX_FILE, data)
    return item


@app.delete("/api/inbox/{item_id}")
def delete_inbox_item(item_id: str) -> dict:
    data = load_versioned(INBOX_FILE)
    for it in data.setdefault("items", []):
        if it["id"] == item_id and _is_live(it):
            it["deletedAt"] = time.time()
            save_versioned(INBOX_FILE, data)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="inbox item not found")


@app.post("/api/inbox/{item_id}/restore", response_model=InboxItem)
def restore_inbox_item(item_id: str) -> InboxItem:
    data = load_versioned(INBOX_FILE)
    for it in data.setdefault("items", []):
        if it["id"] == item_id:
            it["deletedAt"] = None
            save_versioned(INBOX_FILE, data)
            return InboxItem(**it)
    raise HTTPException(status_code=404, detail="inbox item not found")


# --- Activity log (momentum gauge) -----------------------------------------


def _read_activity() -> dict:
    """Activity log as {"version": 1, "days": {date: count}}, tolerant of a
    missing/empty file."""
    try:
        data = read_json(ACTIVITY_FILE)
    except FileNotFoundError:
        data = {}
    days = data.get("days")
    if not isinstance(days, dict):
        days = {}
    return {"version": 1, "days": days}


@app.get("/api/activity")
def get_activity() -> dict:
    return {"days": _read_activity()["days"]}


@app.post("/api/activity")
def post_activity() -> dict:
    """Record one unit of activity for the server's local 'today'. Any app
    open or meaningful action calls this; the per-day count drives the
    momentum gauge + mosaic."""
    data = _read_activity()
    today = _dt.date.today().isoformat()
    days = data["days"]
    days[today] = int(days.get(today, 0)) + 1
    write_json(ACTIVITY_FILE, data)
    return {"date": today, "count": days[today]}


class TaskSchedule(BaseModel):
    date: str
    startMin: int = Field(ge=0, le=24 * 60)
    durationMin: int = Field(ge=1, le=24 * 60)

    @field_validator("date")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("schedule.date must be YYYY-MM-DD")
        return v


DEFAULT_DURATION_MIN = 30

# Tier 2 #15: lowercase 3-letter weekday tokens for recurSchedule.days.
WEEKDAY_TOKENS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class RecurSchedule(BaseModel):
    """Recurrence spec (Tier 2 #15 + granularity epic #25).

    Two flavors, distinguished by ``startMin``:
      - **Timed** (``startMin`` set): projects onto each matching day at the
        same ``startMin`` / ``durationMin`` without a per-day schedule write
        (display-only until the user drags/edits it). Lives on the timeline.
      - **Un-timed** (``startMin`` is ``None``): no clock time, no timeline
        projection — the task shows in the Queue on matching days and is
        derived-hidden on off-days. ``durationMin`` is irrelevant and forced
        to ``None``.

    ``days`` is a list of weekday tokens, or ``None`` for every day.
    """

    startMin: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    durationMin: Optional[int] = Field(default=None, ge=1, le=24 * 60)
    days: Optional[List[str]] = None

    @field_validator("days")
    @classmethod
    def _validate_days(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        for d in v:
            if d not in WEEKDAY_TOKENS:
                raise ValueError(f"recurSchedule.days entries must be one of {WEEKDAY_TOKENS}")
        return v

    @model_validator(mode="after")
    def _normalize_time(self) -> "RecurSchedule":
        # Un-timed (no startMin) → no durationMin. Timed but missing a
        # duration → fall back to the default block length.
        if self.startMin is None:
            self.durationMin = None
        elif self.durationMin is None:
            self.durationMin = DEFAULT_DURATION_MIN
        return self


def _validate_date_list(v: Optional[List[str]]) -> List[str]:
    """Shared validator body for recurExceptions — every entry YYYY-MM-DD."""
    if not v:
        return []
    for d in v:
        if not DATE_RE.match(d):
            raise ValueError("recurExceptions entries must be YYYY-MM-DD")
    return list(v)


class TaskRecord(BaseModel):
    id: str
    title: str
    priority: str = "medium"
    notes: Optional[str] = None
    schedule: Optional[TaskSchedule] = None
    done: bool = False
    tags: List[str] = Field(default_factory=list)
    defaultDurationMin: int = Field(default=DEFAULT_DURATION_MIN, ge=1, le=24 * 60)
    # Tier 2 #12 additions ---
    dueDate: Optional[str] = None
    recurring: bool = False
    snoozedUntil: Optional[float] = None
    # Tier 2 #15 additions ---
    recurSchedule: Optional[RecurSchedule] = None
    recurExceptions: List[str] = Field(default_factory=list)
    # ---
    createdAt: float
    updatedAt: float
    completedAt: Optional[float] = None
    deletedAt: Optional[float] = None

    @field_validator("dueDate")
    @classmethod
    def _validate_due_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not DATE_RE.match(v):
            raise ValueError("dueDate must be YYYY-MM-DD")
        return v

    @field_validator("recurExceptions")
    @classmethod
    def _validate_exceptions(cls, v: Optional[List[str]]) -> List[str]:
        return _validate_date_list(v)


class TaskCreateIn(BaseModel):
    title: str
    priority: str = "medium"
    notes: Optional[str] = None
    schedule: Optional[TaskSchedule] = None
    done: bool = False
    tags: List[str] = Field(default_factory=list)
    defaultDurationMin: Optional[int] = Field(default=None, ge=1, le=24 * 60)
    dueDate: Optional[str] = None
    recurring: bool = False
    snoozedUntil: Optional[float] = None
    recurSchedule: Optional[RecurSchedule] = None
    recurExceptions: List[str] = Field(default_factory=list)

    @field_validator("dueDate")
    @classmethod
    def _validate_due_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not DATE_RE.match(v):
            raise ValueError("dueDate must be YYYY-MM-DD")
        return v

    @field_validator("recurExceptions")
    @classmethod
    def _validate_exceptions(cls, v: Optional[List[str]]) -> List[str]:
        return _validate_date_list(v)


class TaskPatchIn(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    schedule: Optional[TaskSchedule] = None
    done: Optional[bool] = None
    tags: Optional[List[str]] = None
    defaultDurationMin: Optional[int] = Field(default=None, ge=1, le=24 * 60)
    dueDate: Optional[str] = None
    recurring: Optional[bool] = None
    snoozedUntil: Optional[float] = None
    recurSchedule: Optional[RecurSchedule] = None
    recurExceptions: Optional[List[str]] = None

    @field_validator("dueDate")
    @classmethod
    def _validate_due_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not DATE_RE.match(v):
            raise ValueError("dueDate must be YYYY-MM-DD")
        return v

    @field_validator("recurExceptions")
    @classmethod
    def _validate_exceptions(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        return _validate_date_list(v)


def validate_priority(priority: str) -> None:
    if priority not in TASK_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {TASK_PRIORITIES}")


@app.get("/api/tasks")
def get_tasks() -> dict:
    data = load_versioned(TASKS_FILE)
    live = [_normalize_task(i) for i in data.get("items", []) if _is_live(i)]
    items = sorted(live, key=lambda i: i["createdAt"], reverse=True)
    return {"items": items}


@app.post("/api/tasks", response_model=TaskRecord)
def create_task(payload: TaskCreateIn) -> TaskRecord:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="empty title")
    validate_priority(payload.priority)
    notes = payload.notes.strip() if payload.notes else None
    now = time.time()
    # Prefer explicit defaultDurationMin; otherwise sync to the schedule's
    # durationMin so the task's "last used" duration matches reality.
    if payload.defaultDurationMin is not None:
        default_duration = payload.defaultDurationMin
    elif payload.schedule is not None:
        default_duration = payload.schedule.durationMin
    else:
        default_duration = DEFAULT_DURATION_MIN
    rec = TaskRecord(
        id=new_id(),
        title=title,
        priority=payload.priority,
        notes=notes or None,
        schedule=payload.schedule,
        done=payload.done,
        tags=list(payload.tags),
        defaultDurationMin=default_duration,
        dueDate=payload.dueDate,
        recurring=payload.recurring,
        snoozedUntil=payload.snoozedUntil,
        recurSchedule=payload.recurSchedule,
        recurExceptions=list(payload.recurExceptions),
        createdAt=now,
        updatedAt=now,
        completedAt=now if payload.done else None,
    )
    data = load_versioned(TASKS_FILE)
    data.setdefault("items", []).append(rec.model_dump())
    save_versioned(TASKS_FILE, data)
    return rec


@app.patch("/api/tasks/{task_id}", response_model=TaskRecord)
def patch_task(task_id: str, payload: TaskPatchIn) -> TaskRecord:
    data = load_versioned(TASKS_FILE)
    fields = payload.model_fields_set
    for it in data.setdefault("items", []):
        if it["id"] == task_id and _is_live(it):
            _normalize_task(it)
            if "title" in fields:
                t = (payload.title or "").strip()
                if not t:
                    raise HTTPException(status_code=400, detail="empty title")
                it["title"] = t
            if "priority" in fields:
                validate_priority(payload.priority)
                it["priority"] = payload.priority
            if "notes" in fields:
                if payload.notes is None:
                    it["notes"] = None
                else:
                    stripped = payload.notes.strip()
                    it["notes"] = stripped or None
            if "schedule" in fields:
                it["schedule"] = payload.schedule.model_dump() if payload.schedule else None
                # When the user resizes (or schedules with a new duration),
                # remember it as the task's preferred duration so the next
                # auto-schedule uses the same slot length. Unscheduling
                # (schedule -> None) leaves defaultDurationMin alone.
                if payload.schedule is not None:
                    it["defaultDurationMin"] = payload.schedule.durationMin
            if "tags" in fields:
                it["tags"] = list(payload.tags or [])
            if "defaultDurationMin" in fields:
                it["defaultDurationMin"] = int(payload.defaultDurationMin)
            if "dueDate" in fields:
                it["dueDate"] = payload.dueDate
            if "recurring" in fields:
                it["recurring"] = bool(payload.recurring)
            if "snoozedUntil" in fields:
                it["snoozedUntil"] = (
                    None if payload.snoozedUntil is None else float(payload.snoozedUntil)
                )
            if "recurSchedule" in fields:
                it["recurSchedule"] = (
                    payload.recurSchedule.model_dump()
                    if payload.recurSchedule
                    else None
                )
            if "recurExceptions" in fields:
                # Replace-all semantics, mirroring tags. Explicit null clears.
                it["recurExceptions"] = list(payload.recurExceptions or [])
            now = time.time()
            if "done" in fields:
                new_done = bool(payload.done)
                prev_done = bool(it.get("done", False))
                is_recurring = bool(it.get("recurring", False))
                it["done"] = new_done
                # For non-recurring tasks completedAt only moves on a state
                # transition. For recurring tasks each PATCH done:true
                # refreshes the timestamp so the wins counter picks up the
                # new day's completion (the prior cycle's completedAt is
                # lost — defer history tracking to the stats modal).
                if new_done and (not prev_done or is_recurring):
                    it["completedAt"] = now
                elif prev_done and not new_done:
                    it["completedAt"] = None
            it["updatedAt"] = now
            save_versioned(TASKS_FILE, data)
            return TaskRecord(**it)
    raise HTTPException(status_code=404, detail="task not found")


@app.delete("/api/tasks/{task_id}")
def delete_task_record(task_id: str) -> dict:
    data = load_versioned(TASKS_FILE)
    for it in data.setdefault("items", []):
        if it["id"] == task_id and _is_live(it):
            it["deletedAt"] = time.time()
            save_versioned(TASKS_FILE, data)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="task not found")


@app.post("/api/tasks/{task_id}/restore", response_model=TaskRecord)
def restore_task_record(task_id: str) -> TaskRecord:
    data = load_versioned(TASKS_FILE)
    for it in data.setdefault("items", []):
        if it["id"] == task_id:
            _normalize_task(it)
            it["deletedAt"] = None
            save_versioned(TASKS_FILE, data)
            return TaskRecord(**it)
    raise HTTPException(status_code=404, detail="task not found")


@app.get("/api/day/{date}")
def get_day(date: str) -> dict:
    if not DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="bad date format, expected YYYY-MM-DD")
    data = load_versioned(TASKS_FILE)
    tasks_for_day = [
        _normalize_task(t) for t in data.get("items", [])
        if _is_live(t) and t.get("schedule") and t["schedule"].get("date") == date
    ]
    return {"tasks": tasks_for_day}


@app.get("/api/calendar/events")
def get_calendar_events(date: str) -> dict:
    """Read-only overlay of external events for the requested local-date day.

    Source: ``data/UserCalendar/*.ics``. The directory is gitignored so the
    calendar contents never leave the machine. Multi-day timed events are
    clipped to the day's window; multi-day all-day events appear on each day
    they span.
    """
    if not DATE_RE.match(date):
        raise HTTPException(
            status_code=400, detail="bad date format, expected YYYY-MM-DD"
        )
    return {"events": calendar_overlay.events_for_date(date, CALENDAR_DIR)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


# The browser's ES module registry plus default HTTP caching combine into a
# nasty foot-gun for local iteration: edits to `web/*.js` get served back via
# 304-Not-Modified, the registry returns the cached parsed module, and the
# page silently uses the stale code. For a single-user local app there's no
# perf reason to cache, so disable it. (No-store also makes preview reloads
# Just Work without the user remembering Cmd-Shift-R.)
class _NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store"
        return response


app.mount("/web", _NoCacheStaticFiles(directory=str(WEB)), name="web")


if __name__ == "__main__":
    import uvicorn

    print(f"ADHD assistant: http://localhost:{PORT}")
    uvicorn.run("server:app", host="127.0.0.1", port=PORT, reload=False)
