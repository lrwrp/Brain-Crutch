// Focus queue: one task at a time.
//
// A full-screen overlay (modeled on the focus timer's overlay) that presents a
// single task to work on, with two actions: Complete and Skip. The queue is a
// snapshot of *today's* actionable work, taken when the overlay opens:
//
//   - scheduled on today (a real schedule.date === today, OR a sticky
//     recurrence that projects onto today), OR
//   - due today / overdue (dueDate <= today),
//   and in every case NOT snoozed and NOT already done-today.
//
// Ordering: timed items first (by start time), then untimed — overdue ahead of
// due-today, then by priority. The snapshot is an array of task ids; the head
// (index 0) is always "current".
//
//   Complete → PATCH {done:true}, drop the head, show the next.
//   Skip     → move the head to the BACK of the queue (you cycle; nothing is
//              lost), show the next.
//
// State machine: idle | running | empty. Completing the last item (or skipping
// when there's nothing else) drains to the empty "all clear" state.

import {
  queueBtn,
  queueOverlayEl,
  queueExitBtn,
  queueStateRunningEl,
  queueStateEmptyEl,
  queueProgressEl,
  queuePriorityEl,
  queueDueEl,
  queueTitleEl,
  queueScheduleEl,
  queueNotesEl,
  queueSkipBtn,
  queueCompleteBtn,
  queueEmptyCloseBtn,
} from "./dom.js";
import {
  tasks,
  getTask,
  upsertTaskLocal,
  priorityOf,
  PRIORITY_ORDER,
  isDoneToday,
  isSnoozedNow,
  isScheduledToday,
  projectedScheduleFor,
} from "./state.js";
import { patchTaskRecord } from "./api.js";
import { plaintextPreview } from "./markdown.js";
import { todayKey, fmtMin, formatDueDate } from "./time.js";
import { showToast } from "./toast.js";

let state = "idle"; // idle | running | empty
let queue = []; // array of task ids; queue[0] is the current task
let busy = false; // guards against double Complete while a PATCH is in flight

// ----- Queue construction --------------------------------------------------

// The start-minute for a task on today's timeline, or null if it isn't timed
// today. A real schedule on today's key wins; otherwise a sticky projection.
function todayStartMin(task) {
  if (isScheduledToday(task)) return task.schedule.startMin;
  const proj = projectedScheduleFor(task, todayKey());
  return proj ? proj.startMin : null;
}

function isTodayRelevant(task) {
  if (isSnoozedNow(task) || isDoneToday(task)) return false;
  if (todayStartMin(task) !== null) return true;
  // Due today or overdue (YYYY-MM-DD compares lexicographically).
  if (task.dueDate && task.dueDate <= todayKey()) return true;
  return false;
}

function buildQueue() {
  const today = todayKey();
  const items = tasks.filter(isTodayRelevant);
  items.sort((a, b) => {
    const sa = todayStartMin(a);
    const sb = todayStartMin(b);
    // Timed items come first, ordered by start time.
    if (sa !== null && sb !== null) return sa - sb;
    if (sa !== null) return -1;
    if (sb !== null) return 1;
    // Both untimed: overdue ahead of due-today, then by priority.
    const oa = a.dueDate && a.dueDate < today ? 0 : 1;
    const ob = b.dueDate && b.dueDate < today ? 0 : 1;
    if (oa !== ob) return oa - ob;
    return (PRIORITY_ORDER[priorityOf(a)] ?? 1) - (PRIORITY_ORDER[priorityOf(b)] ?? 1);
  });
  return items.map((t) => t.id);
}

// ----- Rendering -----------------------------------------------------------

function showOnlyState(el) {
  for (const e of [queueStateRunningEl, queueStateEmptyEl]) {
    e.classList.toggle("hidden", e !== el);
  }
}

// Render queue[0]. Drops any stale head (task deleted while the overlay was
// open) before painting. Falls through to the empty state when nothing's left.
function renderCurrent() {
  while (queue.length && !getTask(queue[0])) queue.shift();
  if (!queue.length) {
    enterEmpty();
    return;
  }
  const task = getTask(queue[0]);

  queueProgressEl.textContent =
    queue.length === 1 ? "1 left" : `${queue.length} left`;

  queuePriorityEl.dataset.priority = priorityOf(task);
  queuePriorityEl.textContent = priorityOf(task);

  const due = formatDueDate(task.dueDate);
  if (due.text) {
    queueDueEl.className = `queue-due due-date due-${due.urgency}`;
    queueDueEl.textContent = due.text;
    queueDueEl.hidden = false;
  } else {
    queueDueEl.hidden = true;
    queueDueEl.textContent = "";
  }

  queueTitleEl.textContent = task.title;

  const startMin = todayStartMin(task);
  if (startMin !== null) {
    const sticky = !isScheduledToday(task);
    queueScheduleEl.textContent = `${sticky ? "↻ " : ""}Today ${fmtMin(startMin)}`;
    queueScheduleEl.hidden = false;
  } else {
    queueScheduleEl.hidden = true;
    queueScheduleEl.textContent = "";
  }

  if (task.notes) {
    queueNotesEl.textContent = plaintextPreview(task.notes);
    queueNotesEl.hidden = false;
  } else {
    queueNotesEl.hidden = true;
    queueNotesEl.textContent = "";
  }
}

// ----- State transitions ---------------------------------------------------

export function isQueueActive() {
  return state !== "idle";
}

export function openQueue() {
  queue = buildQueue();
  busy = false;
  queueOverlayEl.classList.remove("hidden");
  if (!queue.length) {
    enterEmpty();
  } else {
    state = "running";
    showOnlyState(queueStateRunningEl);
    renderCurrent();
  }
}

function enterEmpty() {
  state = "empty";
  showOnlyState(queueStateEmptyEl);
}

export function closeQueue() {
  queueOverlayEl.classList.add("hidden");
  state = "idle";
  queue = [];
  busy = false;
}

function skipCurrent() {
  if (state !== "running" || !queue.length) return;
  const id = queue.shift();
  queue.push(id); // send to the back of the line
  renderCurrent();
}

async function completeCurrent() {
  if (state !== "running" || busy || !queue.length) return;
  busy = true;
  queueCompleteBtn.disabled = true;
  queueSkipBtn.disabled = true;
  try {
    const id = queue[0];
    const updated = await patchTaskRecord(id, { done: true });
    if (!updated) {
      showToast("Save failed");
      return;
    }
    upsertTaskLocal(updated); // refreshes triage + timeline + wins via the bus
    queue.shift();
    renderCurrent();
  } finally {
    busy = false;
    queueCompleteBtn.disabled = false;
    queueSkipBtn.disabled = false;
  }
}

// ----- Keyboard (called from keyboard.js while the overlay is active) ------

export function handleQueueKey(e) {
  if (state === "empty") {
    if (e.key === "Enter") {
      e.preventDefault();
      closeQueue();
    }
    return;
  }
  if (state !== "running") return;
  if (e.key === "c" || e.key === "C" || e.key === "Enter") {
    e.preventDefault();
    completeCurrent();
  } else if (e.key === "s" || e.key === "S") {
    e.preventDefault();
    skipCurrent();
  }
}

// ----- Wiring --------------------------------------------------------------

export function initQueue() {
  queueBtn.addEventListener("click", openQueue);
  queueExitBtn.addEventListener("click", closeQueue);
  queueEmptyCloseBtn.addEventListener("click", closeQueue);
  queueSkipBtn.addEventListener("click", skipCurrent);
  queueCompleteBtn.addEventListener("click", completeCurrent);
}
