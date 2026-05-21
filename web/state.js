// Client-side state: the canonical `tasks` array, the derived `dayTasks`
// flattened view, current date, and the selected task id. Mutation helpers
// emit on ``events.bus`` so renderers (timeline, triage) refresh only when
// their event of interest fires. ``dayTasks`` is kept up-to-date internally
// via ``recomputeDayView`` so drag/resize collision checks (``overlaps``)
// always see the latest schedule.

import { todayKey } from "./time.js";
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

// ----- Derived day view -----

function deriveDayTasks() {
  return tasks
    .filter((t) => t.schedule && t.schedule.date === currentDate)
    .map((t) => ({
      id: t.id,
      title: t.title,
      startMin: t.schedule.startMin,
      durationMin: t.schedule.durationMin,
      done: !!t.done,
      notes: t.notes || null,
      priority: priorityOf(t),
    }))
    .sort((a, b) => a.startMin - b.startMin);
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
