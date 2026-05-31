// Client-side state: the canonical `tasks` array, the derived `dayTasks`
// flattened view, current date, and the selected task id. Mutation helpers
// emit on ``events.bus`` so renderers (timeline, triage) refresh only when
// their event of interest fires. ``dayTasks`` is kept up-to-date internally
// via ``recomputeDayView`` so drag/resize collision checks (``overlaps``)
// always see the latest schedule.

import { todayKey, parseDateKey } from "./time.js";
import { bus, EVENTS } from "./events.js";

export let tasks = [];
export let dayTasks = [];
export let currentDate = todayKey();
export let selectedTaskId = null;

const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };
const PRIORITY_CYCLE = ["low", "medium", "high"];

export { PRIORITY_ORDER, PRIORITY_CYCLE };

export function priorityOf(t) {
  return t && PRIORITY_ORDER[t.priority] !== undefined ? t.priority : "medium";
}

export function shiftPriority(current, delta) {
  const idx = PRIORITY_CYCLE.indexOf(current);
  const start = idx < 0 ? 1 : idx;
  const next = Math.max(0, Math.min(PRIORITY_CYCLE.length - 1, start + delta));
  return PRIORITY_CYCLE[next];
}

// ----- Sticky-time recurrence projection (Tier 2 #15) -----

// Sunday-indexed weekday tokens, matching the server's WEEKDAY_TOKENS set.
// getDay() returns 0=Sun … 6=Sat, so index straight into this array.
const WEEKDAY_TOKENS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

// If `task` carries a recurSchedule that lands on `dateKey`, return the
// projected day-schedule ``{date, startMin, durationMin}``; otherwise null.
// A projection is suppressed when:
//   - the task is explicitly scheduled on that day already (the real
//     schedule wins — dragging a sticky block "solidifies" it for the day),
//   - the day is listed in recurExceptions (a one-day skip), or
//   - the weekday isn't in recurSchedule.days (null/empty days = every day).
// The projection is display-only: it never writes a schedule to disk until
// the user drags/edits the block.
export function projectedScheduleFor(task, dateKey) {
  if (!task || !task.recurSchedule) return null;
  if (task.schedule && task.schedule.date === dateKey) return null;
  if (
    Array.isArray(task.recurExceptions) &&
    task.recurExceptions.includes(dateKey)
  ) {
    return null;
  }
  const rs = task.recurSchedule;
  const days = rs.days;
  if (Array.isArray(days) && days.length) {
    const token = WEEKDAY_TOKENS[parseDateKey(dateKey).getDay()];
    if (!days.includes(token)) return null;
  }
  return {
    date: dateKey,
    startMin: rs.startMin,
    durationMin: rs.durationMin,
  };
}

function rangesOverlap(aStart, aDur, bStart, bDur) {
  return aStart < bStart + bDur && aStart + aDur > bStart;
}

// ----- Derived day view -----

function dayEntry(task, schedule, sticky) {
  return {
    id: task.id,
    title: task.title,
    startMin: schedule.startMin,
    durationMin: schedule.durationMin,
    // isDoneToday folds the recurring "resets at midnight" rule in, so a
    // recurring block completed yesterday shows as undone today.
    done: isDoneToday(task),
    notes: task.notes || null,
    priority: priorityOf(task),
    sticky: !!sticky,
  };
}

function deriveDayTasks() {
  const entries = [];
  // Explicit schedules first — they own their slot.
  for (const t of tasks) {
    if (t.schedule && t.schedule.date === currentDate) {
      entries.push(dayEntry(t, t.schedule, false));
    }
  }
  // Then sticky projections, in start-time order, skipping any that would
  // collide with an already-placed block (explicit or an earlier sticky).
  const projections = [];
  for (const t of tasks) {
    if (t.schedule && t.schedule.date === currentDate) continue;
    const proj = projectedScheduleFor(t, currentDate);
    if (proj) projections.push({ task: t, proj });
  }
  projections.sort((a, b) => a.proj.startMin - b.proj.startMin);
  for (const { task, proj } of projections) {
    const conflict = entries.some((e) =>
      rangesOverlap(proj.startMin, proj.durationMin, e.startMin, e.durationMin),
    );
    if (conflict) continue;
    entries.push(dayEntry(task, proj, true));
  }
  return entries.sort((a, b) => a.startMin - b.startMin);
}

function recomputeDayView() {
  dayTasks = deriveDayTasks();
}

// ----- Tasks mutations -----

export function setTasks(newTasks) {
  tasks = newTasks;
  recomputeDayView();
  // Bulk replace (initial fetch, future bulk imports). Day-changed is the
  // closest event in spirit — renderers re-render the full day view.
  bus.emit(EVENTS.DAY_CHANGED, { date: currentDate, bulk: true });
}

export function upsertTaskLocal(rec) {
  const idx = tasks.findIndex((t) => t.id === rec.id);
  const isNew = idx < 0;
  if (isNew) tasks.unshift(rec);
  else tasks[idx] = rec;
  recomputeDayView();
  // Detect done-flip so the future wins counter (Phase 5) can subscribe to
  // TASK_COMPLETED alone, not TASK_CHANGED. We don't have the pre-image here,
  // so completion is "looks done and the change touched it" — refined later
  // when the server returns completedAt and we compare.
  if (rec.done) bus.emit(EVENTS.TASK_COMPLETED, { id: rec.id, task: rec });
  bus.emit(isNew ? EVENTS.TASK_CREATED : EVENTS.TASK_CHANGED, {
    id: rec.id,
    task: rec,
  });
}

export function removeTaskLocal(id) {
  tasks = tasks.filter((t) => t.id !== id);
  recomputeDayView();
  bus.emit(EVENTS.TASK_DELETED, { id });
}

export function getTask(id) {
  return tasks.find((t) => t.id === id);
}

// True when the task should display as completed in the current day's UI:
//   - non-recurring: the raw `done` flag is canonical (a checked-off task
//     stays checked off until explicitly un-checked).
//   - recurring: only "done for today" if completedAt falls within the
//     current local day. Yesterday's completion → undone (ready to be
//     re-completed). The wins counter already keys off `completedAt` for
//     "today's wins" purposes, so each daily re-completion bumps wins.
export function isDoneToday(task) {
  if (!task || !task.done) return false;
  if (!task.recurring) return true;
  if (typeof task.completedAt !== "number") return false;
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  return task.completedAt * 1000 >= startOfToday.getTime();
}

// True when the task's snoozedUntil is in the future (i.e. currently hidden).
export function isSnoozedNow(task) {
  if (!task || typeof task.snoozedUntil !== "number") return false;
  return task.snoozedUntil * 1000 > Date.now();
}

// True when the task currently has a schedule on the local-today key.
// Companion to isDoneToday / isSnoozedNow — keeps the "what does the
// schedule shape look like" knowledge in one place so callers can ask
// the question without reaching into task.schedule.date themselves.
export function isScheduledToday(task) {
  return !!(task && task.schedule && task.schedule.date === todayKey());
}

// True when the task's schedule.date is in the past and it hasn't been
// done for that day. Used by the Tasks-tab row to flag rolled-over work
// (Tier 2 #6) so the user sees "this got missed yesterday."
export function isRolledOver(task) {
  if (!task || !task.schedule) return false;
  if (task.schedule.date >= todayKey()) return false; // YYYY-MM-DD lexicographic compare
  return !isDoneToday(task);
}

// True when the task is "completed" in a way that lets the Tasks tab
// hide it under the "Completed (N)" disclosure (Tier 2 #6). Recurring
// tasks stay visible even when checked done today — that's the whole
// point of the recurring affordance — so this returns false for them.
export function isHidableComplete(task) {
  return !!task && !task.recurring && task.done;
}

// Lightweight view used by slot-finding code. Keeps only the geometry fields
// findFreeSlotIn needs, so the slot search doesn't accidentally mutate other
// task properties.
export function tasksScheduledOn(dateStr) {
  return tasks
    .filter((t) => t.schedule && t.schedule.date === dateStr)
    .map((t) => ({
      id: t.id,
      title: t.title,
      startMin: t.schedule.startMin,
      durationMin: t.schedule.durationMin,
    }));
}

// ----- Day-view overlap check (used by drag/resize) -----

export function overlaps(startMin, duration, excludeId) {
  const end = startMin + duration;
  return dayTasks.some(
    (t) =>
      t.id !== excludeId && startMin < t.startMin + t.durationMin && end > t.startMin,
  );
}

// ----- Current date -----

export function setCurrentDate(d) {
  currentDate = d;
  recomputeDayView();
  bus.emit(EVENTS.DAY_CHANGED, { date: d });
}

// ----- Selection -----

export function setSelectedTask(id) {
  if (selectedTaskId === id) return;
  selectedTaskId = id;
  refreshSelectionDom();
}

export function clearSelection() {
  if (selectedTaskId === null) return;
  selectedTaskId = null;
  refreshSelectionDom();
}

function refreshSelectionDom() {
  document
    .querySelectorAll(".task-block.selected, .triage-item.selected")
    .forEach((el) => el.classList.remove("selected"));
  if (selectedTaskId === null) return;
  document
    .querySelectorAll(`[data-id="${CSS.escape(selectedTaskId)}"]`)
    .forEach((el) => {
      if (
        el.classList.contains("task-block") ||
        el.classList.contains("triage-item")
      ) {
        el.classList.add("selected");
      }
    });
}
