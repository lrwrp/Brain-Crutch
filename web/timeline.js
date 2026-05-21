// Day timeline: hour labels, "now" line, task blocks, drag/resize/title-edit,
// and the schedule/unschedule helpers that toggle whether a task lives on the
// current day. Subscribes to task + day events on ``events.bus`` so the day
// view re-renders on any task mutation.

import { bus, EVENTS } from "./events.js";
import {
  timelineEl,
  hoursEl,
  tracksEl,
  nowLineEl,
  nowPillEl,
  addBtn,
} from "./dom.js";
import {
  dayTasks,
  currentDate,
  selectedTaskId,
  getTask,
  upsertTaskLocal,
  overlaps,
  setSelectedTask,
  tasksScheduledOn,
} from "./state.js";
import { patchTaskRecord } from "./api.js";
import {
  TIMELINE_START_MIN,
  TIMELINE_END_MIN,
  PX_PER_MIN,
  SNAP_MIN,
  MIN_DURATION_MIN,
  DEFAULT_DURATION_MIN,
  todayKey,
  nowMinutes,
  fmtMin,
  snap,
  clampStart,
  describeDay,
  findFreeSlotIn,
  nearestFreeSlot,
} from "./time.js";
import { showToast } from "./toast.js";
import { makePriorityStripe, notesIcon } from "./triage.js";
import { openCaptureModal } from "./modal.js";

// ----- Static scaffolding -----

function renderHourLabels() {
  hoursEl.innerHTML = "";
  // Render every hour across the full 24h canvas. The 08-20 focus is
  // expressed via the default scroll position, not by hiding labels.
  for (let m = TIMELINE_START_MIN; m < TIMELINE_END_MIN; m += 60) {
    const label = document.createElement("div");
    label.className = "hour-label";
    label.style.top = `${(m - TIMELINE_START_MIN) * PX_PER_MIN}px`;
    label.textContent = fmtMin(m);
    hoursEl.appendChild(label);
  }
}

export function updateNowLine() {
  const isToday = currentDate === todayKey();
  if (!isToday) {
    nowLineEl.classList.add("off");
    for (const block of tracksEl.querySelectorAll(".task-block.current")) {
      block.classList.remove("current");
    }
    return;
  }
  const now = nowMinutes();
  // Now-line works the full 24 hours.
  if (now < TIMELINE_START_MIN || now > TIMELINE_END_MIN) {
    nowLineEl.classList.add("off");
    return;
  }
  nowLineEl.classList.remove("off");
  const top = (now - TIMELINE_START_MIN) * PX_PER_MIN;
  nowLineEl.style.top = `${top}px`;
  nowPillEl.textContent = fmtMin(now);
  for (const block of tracksEl.querySelectorAll(".task-block")) {
    const start = Number(block.dataset.start);
    const end = start + Number(block.dataset.duration);
    block.classList.toggle("current", now >= start && now < end);
  }
}

// ----- Block rendering -----

function applyBlockGeometry(el, startMin, durationMin) {
  // Top is measured from the canvas origin (TIMELINE_START_MIN) so that
  // blocks at 00:00 sit at y=0 and the layout matches the hour labels.
  el.style.top = `${(startMin - TIMELINE_START_MIN) * PX_PER_MIN}px`;
  el.style.height = `${durationMin * PX_PER_MIN}px`;
  el.dataset.start = String(startMin);
  el.dataset.duration = String(durationMin);
  const timeEl = el.querySelector(".task-time");
  if (timeEl) {
    timeEl.textContent = `${fmtMin(startMin)}–${fmtMin(startMin + durationMin)} · ${durationMin}m`;
  }
}

function renderTasks() {
  for (const el of tracksEl.querySelectorAll(".task-block")) el.remove();
  for (const t of dayTasks) tracksEl.appendChild(renderTaskBlock(t));
  updateNowLine();
}

function renderTaskBlock(task) {
  const el = document.createElement("div");
  el.className = "task-block";
  if (task.done) el.classList.add("done");
  el.dataset.id = task.id;
  el.dataset.priority = task.priority;
  if (task.id === selectedTaskId) el.classList.add("selected");

  const stripe = makePriorityStripe(task.id, task.priority);
  el.appendChild(stripe);

  const title = document.createElement("div");
  title.className = "task-title";
  title.textContent = task.title;

  const meta = document.createElement("div");
  meta.className = "task-meta";
  const blockNotes = notesIcon(task);
  if (blockNotes) {
    blockNotes.style.marginRight = "4px";
    meta.appendChild(blockNotes);
  }
  const timeSpan = document.createElement("span");
  timeSpan.className = "task-time";
  meta.appendChild(timeSpan);

  const actions = document.createElement("div");
  actions.className = "task-actions";

  // Done toggle: ○ when not done, ✓ when done. pointerdown stopPropagation
  // keeps the drag handler from kicking in when the user clicks the button.
  const doneToggle = document.createElement("button");
  doneToggle.type = "button";
  doneToggle.className = "task-action done-toggle" + (task.done ? " done" : "");
  doneToggle.title = task.done ? "Mark not done" : "Mark done";
  doneToggle.textContent = task.done ? "✓" : "○";
  doneToggle.addEventListener("pointerdown", (e) => e.stopPropagation());
  doneToggle.addEventListener("click", async (e) => {
    e.stopPropagation();
    const updated = await patchTaskRecord(task.id, { done: !task.done });
    if (!updated) {
      showToast("Save failed");
      return;
    }
    upsertTaskLocal(updated);
  });

  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "task-action";
  edit.title = "Rename";
  edit.textContent = "✎";
  edit.addEventListener("pointerdown", (e) => e.stopPropagation());
  edit.addEventListener("click", (e) => {
    e.stopPropagation();
    beginTitleEdit(el, task.id);
  });

  const del = document.createElement("button");
  del.type = "button";
  del.className = "task-action danger";
  del.title = "Remove from this day (task stays in Tasks tab)";
  del.textContent = "×";
  del.addEventListener("pointerdown", (e) => e.stopPropagation());
  del.addEventListener("click", (e) => {
    e.stopPropagation();
    unscheduleTask(task.id);
  });

  actions.appendChild(doneToggle);
  actions.appendChild(edit);
  actions.appendChild(del);

  const handle = document.createElement("div");
  handle.className = "resize-handle";
  handle.addEventListener("pointerdown", (e) => beginResize(e, el, task.id));

  el.appendChild(title);
  el.appendChild(meta);
  el.appendChild(actions);
  el.appendChild(handle);

  applyBlockGeometry(el, task.startMin, task.durationMin);

  el.addEventListener("pointerdown", (e) => beginDrag(e, el, task.id));
  return el;
}

// ----- Schedule / unschedule helpers -----

export function addTask() {
  const slot = findFreeSlotIn(
    tasksScheduledOn(currentDate),
    currentDate,
    DEFAULT_DURATION_MIN,
  );
  if (!slot) {
    showToast("No free time left on this day");
    return;
  }
  openCaptureModal("day-task", { date: currentDate, slot });
}

async function unscheduleTask(id) {
  const updated = await patchTaskRecord(id, { schedule: null });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
  showToast("Removed from " + describeDay(currentDate).toLowerCase());
}

export async function scheduleTaskOnToday(taskId) {
  const today = todayKey();
  // Honor the task's remembered duration so re-scheduling restores the slot
  // length the user last set, not the constant default.
  const rec = getTask(taskId);
  const preferred = rec?.defaultDurationMin ?? DEFAULT_DURATION_MIN;
  const slot = findFreeSlotIn(tasksScheduledOn(today), today, preferred);
  if (!slot) {
    showToast("No free time left today");
    return false;
  }
  const updated = await patchTaskRecord(taskId, {
    schedule: { date: today, startMin: slot.startMin, durationMin: slot.durationMin },
  });
  if (!updated) {
    showToast("Save failed");
    return false;
  }
  upsertTaskLocal(updated);
  showToast("Scheduled today");
  return true;
}

// ----- Drag -----

function beginDrag(e, el, id) {
  if (e.button !== 0) return;
  if (el.classList.contains("editing")) return;
  if (e.target.closest(".task-action") || e.target.closest(".resize-handle")) return;
  e.preventDefault();
  const dayTask = dayTasks.find((t) => t.id === id);
  if (!dayTask) return;
  const startY = e.clientY;
  const originalStart = dayTask.startMin;
  const duration = dayTask.durationMin;
  let proposedStart = originalStart;
  let moved = false;

  el.setPointerCapture(e.pointerId);
  el.classList.add("dragging");

  function onMove(ev) {
    const deltaPx = ev.clientY - startY;
    if (!moved && Math.abs(deltaPx) < 2) return;
    moved = true;
    let next = snap(originalStart + deltaPx / PX_PER_MIN);
    next = clampStart(next, duration);
    if (next !== proposedStart) {
      proposedStart = next;
      applyBlockGeometry(el, proposedStart, duration);
    }
  }

  function onUp() {
    el.removeEventListener("pointermove", onMove);
    el.removeEventListener("pointerup", onUp);
    el.removeEventListener("pointercancel", onUp);
    el.classList.remove("dragging");
    if (!moved) {
      setSelectedTask(id);
      return;
    }
    if (proposedStart === originalStart) return;
    // Slide-past: if the released position overlaps, search outward for the
    // nearest fitting slot. Only fall back to revert when the day is genuinely
    // full — i.e. the task can't fit anywhere.
    const others = dayTasks.filter((t) => t.id !== id);
    const target = nearestFreeSlot(others, proposedStart, duration);
    if (target === null) {
      applyBlockGeometry(el, originalStart, duration);
      showToast("No free slot in the day");
      return;
    }
    const snapped = target !== proposedStart;
    applyBlockGeometry(el, target, duration);
    const rec = getTask(id);
    if (!rec || !rec.schedule) {
      applyBlockGeometry(el, originalStart, duration);
      return;
    }
    const newSchedule = { ...rec.schedule, startMin: target };
    patchTaskRecord(id, { schedule: newSchedule }).then((updated) => {
      if (!updated) {
        applyBlockGeometry(el, originalStart, duration);
        showToast("Save failed");
        return;
      }
      upsertTaskLocal(updated);
      if (snapped) showToast("Snapped to nearest free slot");
    });
  }

  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerup", onUp);
  el.addEventListener("pointercancel", onUp);
}

// ----- Resize -----

function beginResize(e, el, id) {
  if (e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  const dayTask = dayTasks.find((t) => t.id === id);
  if (!dayTask) return;
  const startY = e.clientY;
  const originalDuration = dayTask.durationMin;
  const startMin = dayTask.startMin;
  let proposedDuration = originalDuration;
  let moved = false;

  el.setPointerCapture(e.pointerId);
  el.classList.add("dragging");

  function onMove(ev) {
    const deltaPx = ev.clientY - startY;
    if (!moved && Math.abs(deltaPx) < 2) return;
    moved = true;
    let next = snap(originalDuration + deltaPx / PX_PER_MIN);
    // Bottom-edge resize is capped by the full timeline so a block can grow
    // past 20:00 into the evening if the user really wants.
    next = Math.max(MIN_DURATION_MIN, Math.min(next, TIMELINE_END_MIN - startMin));
    if (next !== proposedDuration) {
      proposedDuration = next;
      applyBlockGeometry(el, startMin, proposedDuration);
    }
  }

  function onUp() {
    el.removeEventListener("pointermove", onMove);
    el.removeEventListener("pointerup", onUp);
    el.removeEventListener("pointercancel", onUp);
    el.classList.remove("dragging");
    if (!moved || proposedDuration === originalDuration) return;
    if (overlaps(startMin, proposedDuration, id)) {
      applyBlockGeometry(el, startMin, originalDuration);
      showToast("Would overlap next task");
      return;
    }
    const rec = getTask(id);
    if (!rec || !rec.schedule) {
      applyBlockGeometry(el, startMin, originalDuration);
      return;
    }
    const newSchedule = { ...rec.schedule, durationMin: proposedDuration };
    patchTaskRecord(id, { schedule: newSchedule }).then((updated) => {
      if (!updated) {
        applyBlockGeometry(el, startMin, originalDuration);
        showToast("Save failed");
        return;
      }
      upsertTaskLocal(updated);
    });
  }

  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerup", onUp);
  el.addEventListener("pointercancel", onUp);
}

// ----- Inline title edit -----

function beginTitleEdit(el, id) {
  const rec = getTask(id);
  if (!rec) return;
  const titleEl = el.querySelector(".task-title");
  if (!titleEl || el.classList.contains("editing")) return;

  el.classList.add("editing");
  const original = rec.title;

  const inputEl = document.createElement("input");
  inputEl.type = "text";
  inputEl.className = "task-title-input";
  inputEl.value = original;
  titleEl.replaceWith(inputEl);

  let committed = false;
  const finish = async (save) => {
    if (committed) return;
    committed = true;
    el.classList.remove("editing");
    const replacement = document.createElement("div");
    replacement.className = "task-title";
    if (save) {
      const next = inputEl.value.trim();
      if (next && next !== original) {
        const updated = await patchTaskRecord(id, { title: next });
        if (updated) {
          upsertTaskLocal(updated);
          replacement.textContent = updated.title;
          inputEl.replaceWith(replacement);
          return;
        }
        replacement.textContent = original;
        inputEl.replaceWith(replacement);
        showToast("Save failed");
        return;
      }
    }
    replacement.textContent = original;
    inputEl.replaceWith(replacement);
  };

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    }
  });
  inputEl.addEventListener("blur", () => finish(true));
  inputEl.addEventListener("pointerdown", (e) => e.stopPropagation());

  inputEl.focus();
  inputEl.select();
}

// ----- Init -----

// Default scroll target: 07:30 (450 min). Puts ~30 min of pre-dawn time
// above 08:00 so the focus window feels anchored, not cropped at the top.
const DEFAULT_SCROLL_MIN = 450;

function scrollToFocus() {
  // PX_PER_MIN = 1, canvas starts at TIMELINE_START_MIN. Subtract because
  // scrollTop is measured from the top of the scrollable element.
  timelineEl.scrollTop = (DEFAULT_SCROLL_MIN - TIMELINE_START_MIN) * PX_PER_MIN;
}

export function initTimeline() {
  renderHourLabels();
  updateNowLine();
  setInterval(updateNowLine, 30000);
  addBtn.addEventListener("click", addTask);
  // Day-view rerender triggers: any task mutation, plus explicit day changes
  // (date picker, Today, initial setTasks bulk load).
  for (const ev of [
    EVENTS.TASK_CREATED,
    EVENTS.TASK_CHANGED,
    EVENTS.TASK_DELETED,
    EVENTS.DAY_CHANGED,
  ]) {
    bus.on(ev, renderTasks);
  }
  // Re-anchor the focus window every time the day changes — if the user
  // scrolled down to 23:00 yesterday, they probably want today's view to
  // start near 08:00 again. Also handles the initial setTasks bulk load.
  bus.on(EVENTS.DAY_CHANGED, scrollToFocus);
  scrollToFocus();
}
