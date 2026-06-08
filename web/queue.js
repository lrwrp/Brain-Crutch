// Focus queue: one task at a time.
//
// A full-screen overlay (modeled on the focus timer's overlay) that presents a
// single task to work on, with two actions: Complete and Skip. The queue is the
// *un-timed* pile for today: timed tasks live on the timeline, so the queue is
// everything that is NOT on the timeline and is still active —
//
//   - NOT scheduled today (no real schedule.date === today, and no sticky
//     recurrence projecting onto today), AND
//   - NOT snoozed, AND
//   - NOT already done-today.
//
// "Don't want it today? Snooze it." is how things leave the queue. Ordering:
// most-urgent due-date first (overdue → due-today → future → undated), then by
// priority. The snapshot is an array of task ids; the head (index 0) is the
// current card.
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
  queuePeekEl,
  queuePriorityEl,
  queueDurationEl,
  queueDueEl,
  queueTitleEl,
  queueNotesEl,
  queueNotesBtn,
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
  isUntimedRecurHiddenOn,
} from "./state.js";
import { patchTaskRecord } from "./api.js";
import { plaintextPreview } from "./markdown.js";
import {
  todayKey,
  formatDueDate,
  formatDurationBucket,
  DEFAULT_DURATION_MIN,
} from "./time.js";
import { showToast } from "./toast.js";
import { bus, EVENTS } from "./events.js";
import { openNotesReader } from "./notes-read.js";
import { openNotesEditor } from "./notes.js";

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

// The queue is the un-timed pile: a task qualifies when it is NOT on today's
// timeline (no real or sticky-projected schedule) and is still active (not
// snoozed, not done-today).
function isQueueable(task) {
  if (isSnoozedNow(task) || isDoneToday(task)) return false;
  if (todayStartMin(task) !== null) return false; // lives on the timeline
  // Un-timed recurring task on an off-day → derived-hidden (Stage 4).
  if (isUntimedRecurHiddenOn(task, todayKey())) return false;
  return true;
}

function buildQueue() {
  const items = tasks.filter(isQueueable);
  // Most-urgent due-date first; undated tasks sort last. Ties break by priority.
  items.sort((a, b) => {
    const da = a.dueDate || "9999-99-99";
    const db = b.dueDate || "9999-99-99";
    if (da !== db) return da < db ? -1 : 1;
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

const MAX_PEEK = 3;

// Render the upcoming-tasks peek above the active card: a header (title +
// size) per upcoming task, nearest-next closest to the active card (so they
// appear to flow down toward it), with a "+N more" tail beyond the cap. This
// is the at-a-glance "what do I get if I skip?" view.
function renderPeek() {
  queuePeekEl.replaceChildren();
  const upcoming = queue.slice(1).map(getTask).filter(Boolean);
  const shown = upcoming.slice(0, MAX_PEEK);
  const extra = upcoming.length - shown.length;

  if (extra > 0) {
    const more = document.createElement("div");
    more.className = "queue-peek-more";
    more.textContent = `+${extra} more`;
    queuePeekEl.appendChild(more);
  }
  // Furthest first (top), nearest last (just above the active card).
  for (const t of shown.slice().reverse()) {
    const row = document.createElement("div");
    row.className = "queue-peek-card";
    const title = document.createElement("span");
    title.className = "queue-peek-title";
    title.textContent = t.title;
    const dur = document.createElement("span");
    dur.className = "queue-peek-dur";
    dur.textContent = formatDurationBucket(
      t.defaultDurationMin ?? DEFAULT_DURATION_MIN,
    );
    row.append(title, dur);
    queuePeekEl.appendChild(row);
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

  // Size cue: queued tasks are un-timed, so we show the bucketed duration
  // ("< 5" / "30m" / "> 60") as the at-a-glance "how big is this?" signal.
  const durMin = task.defaultDurationMin ?? DEFAULT_DURATION_MIN;
  queueDurationEl.textContent = formatDurationBucket(durMin);

  queueTitleEl.textContent = task.title;

  if (task.notes) {
    queueNotesEl.textContent = plaintextPreview(task.notes);
    queueNotesEl.hidden = false;
  } else {
    queueNotesEl.hidden = true;
    queueNotesEl.textContent = "";
  }

  renderPeek();
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
  } else if (e.key === "r" || e.key === "R") {
    e.preventDefault();
    if (queue.length) openNotesReader(queue[0]);
  } else if (e.key === "e" || e.key === "E") {
    e.preventDefault();
    if (queue.length) openNotesEditor(queue[0]);
  }
}

// ----- Wiring --------------------------------------------------------------

export function initQueue() {
  queueBtn.addEventListener("click", openQueue);
  queueExitBtn.addEventListener("click", closeQueue);
  queueEmptyCloseBtn.addEventListener("click", closeQueue);
  queueSkipBtn.addEventListener("click", skipCurrent);
  queueCompleteBtn.addEventListener("click", completeCurrent);
  queueNotesBtn.addEventListener("click", () => {
    if (state === "running" && queue.length) openNotesReader(queue[0]);
  });
  // Keep the active card fresh when the current task changes elsewhere — e.g.
  // notes edited from within the queue, or its duration stepped. The queue
  // snapshot (the id order) is untouched; only the painted card refreshes.
  bus.on(EVENTS.TASK_CHANGED, () => {
    if (state === "running") renderCurrent();
  });
}
