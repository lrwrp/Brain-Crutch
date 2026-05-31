// Triage panel: tab switching + Inbox rendering + Tasks-tab rendering +
// attach picker. Subscribes to task + day events on ``events.bus`` so the
// tasks-tab list refreshes on any task mutation.

import { bus, EVENTS } from "./events.js";
import { plaintextPreview } from "./markdown.js";
import { openNotesReader } from "./notes-read.js";
import {
  list,
  countEl,
  emptyEl,
  tabButtons,
  tabPanels,
  tasksListEl,
  tasksEmptyEl,
  tasksCountEl,
  tasksSnoozedDetailsEl,
  tasksSnoozedSummaryEl,
  tasksSnoozedListEl,
  tasksCompletedDetailsEl,
  tasksCompletedSummaryEl,
  tasksCompletedListEl,
  taskForm,
  taskInputEl,
  inboxForm,
  inboxInputEl,
} from "./dom.js";
import {
  tasks,
  getTask,
  upsertTaskLocal,
  removeTaskLocal,
  selectedTaskId,
  setSelectedTask,
  priorityOf,
  PRIORITY_CYCLE,
  PRIORITY_ORDER,
  isDoneToday,
  isSnoozedNow,
  isScheduledToday,
  isRolledOver,
  isHidableComplete,
  projectedScheduleFor,
} from "./state.js";
import {
  fetchInbox,
  submitCapture,
  createTaskRecord,
  patchTaskRecord,
  deleteTaskRecord,
  restoreTaskRecord,
  deleteInboxItem,
  restoreInboxItem,
} from "./api.js";
import {
  relativeTime,
  truncateLabel,
  fmtMin,
  describeDay,
  todayKey,
  formatDueDate,
  SNOOZE_PRESETS,
} from "./time.js";
import { showToast, showUndoToast } from "./toast.js";
import { scheduleTaskOnToday } from "./timeline.js";

// ----- Tabs -----

export function switchTab(name) {
  tabButtons.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  tabPanels.forEach((p) => p.classList.toggle("hidden", p.id !== `${name}-panel`));
  try {
    localStorage.setItem("triage-tab", name);
  } catch {}
}

export function initTabs() {
  tabButtons.forEach((b) =>
    b.addEventListener("click", () => switchTab(b.dataset.tab)),
  );
  let saved = null;
  try {
    saved = localStorage.getItem("triage-tab");
  } catch {}
  switchTab(saved === "inbox" || saved === "tasks" ? saved : "tasks");
}

// ----- Inbox helpers -----

function splitInboxItem(item) {
  if (item.url) {
    const rest = ((item.text || "").replace(item.url, "") || "").trim();
    if (rest) return { title: rest, notes: item.url };
    return { title: item.title || item.url, notes: null };
  }
  return { title: item.text || "(untitled)", notes: null };
}

function appendNotes(existing, addition) {
  const a = (existing || "").trim();
  const b = (addition || "").trim();
  if (!a) return b || null;
  if (!b) return a || null;
  return `${a}\n\n${b}`;
}

function inboxItemAsNote(item) {
  const parts = [];
  if (item.title && item.text !== item.title) parts.push(item.title);
  if (item.url && item.text !== item.url) parts.push(item.url);
  if (item.text) parts.push(item.text);
  const seen = new Set();
  const out = [];
  for (const p of parts) {
    const k = p.trim();
    if (!k || seen.has(k)) continue;
    seen.add(k);
    out.push(k);
  }
  return out.join("\n");
}

// ----- Shared row helpers (used by both inbox and tasks-tab rows) -----

export function makeActionButton(label, variant, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "action-btn" + (variant ? ` ${variant}` : "");
  btn.textContent = label;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    let restore = true;
    try {
      const result = await onClick();
      restore = result === false;
    } catch (err) {
      console.error(err);
    }
    if (restore) btn.disabled = false;
  });
  return btn;
}

// Tasks tab and day-block alike use this. `task` carries .id + .notes.
// Returns null when there's nothing to show; otherwise a clickable 📝 that
// opens the notes editor for the underlying task record.
export function notesIcon(task) {
  if (!task || !task.notes) return null;
  const span = document.createElement("span");
  span.className = "notes-icon";
  span.textContent = "📝";
  // Markdown markers ({**, [], etc.}) are stripped before going into the
  // title attribute since the browser can't render HTML in a tooltip.
  span.title = plaintextPreview(task.notes);
  span.style.cursor = "pointer";
  span.addEventListener("pointerdown", (e) => e.stopPropagation());
  span.addEventListener("click", (e) => {
    e.stopPropagation();
    openNotesReader(task.id);
  });
  return span;
}

export function makePriorityStripe(taskId, priority) {
  const stripe = document.createElement("div");
  stripe.className = "priority-stripe";
  stripe.dataset.priority = priority;
  stripe.title = `Priority: ${priority} (click to cycle)`;
  stripe.addEventListener("pointerdown", (e) => e.stopPropagation());
  stripe.addEventListener("click", async (e) => {
    e.stopPropagation();
    await cyclePriorityForTask(taskId);
  });
  return stripe;
}

async function cyclePriorityForTask(taskId) {
  const rec = getTask(taskId);
  if (!rec) return;
  const current = priorityOf(rec);
  const idx = PRIORITY_CYCLE.indexOf(current);
  const next = PRIORITY_CYCLE[(idx + 1) % PRIORITY_CYCLE.length];
  const updated = await patchTaskRecord(taskId, { priority: next });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
}

// scheduleChip removed — Tier 2 #12 replaced the chip-with-× pattern with
// the arrow bar on the row's left edge. Schedule's day + time still appears
// as a sub-line under the task title; see renderTaskRow.

// ----- Inbox rendering -----

function renderInboxItem(item) {
  const li = document.createElement("li");
  li.className = "triage-item";
  li.dataset.id = item.id;

  const textDiv = document.createElement("div");
  textDiv.className = "text";
  if (item.url) {
    const a = document.createElement("a");
    a.href = item.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = item.title || item.url;
    textDiv.appendChild(a);
    if (item.text && item.text !== item.url) {
      const rest = item.text.replace(item.url, "").trim();
      if (rest) {
        const span = document.createElement("span");
        span.textContent = " — " + rest;
        textDiv.appendChild(span);
      }
    }
  } else {
    textDiv.textContent = item.text;
  }

  const row = document.createElement("div");
  row.className = "row";

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = relativeTime(item.createdAt);

  const actions = document.createElement("div");
  actions.className = "triage-actions";

  const pickerHost = document.createElement("div");
  pickerHost.className = "picker-host";

  const attachBtn = makeActionButton("Attach", null, async () => {
    if (pickerHost.firstChild) {
      pickerHost.replaceChildren();
      return false;
    }
    document.querySelectorAll(".picker-host").forEach((h) => h.replaceChildren());
    const picker = buildAttachPicker(item);
    pickerHost.appendChild(picker);
    return false;
  });
  attachBtn.title = "Attach to an existing task as a note";

  const makeBtn = makeActionButton("Make task", "primary", async () => {
    const { title, notes } = splitInboxItem(item);
    const created = await createTaskRecord({ title, status: "active", notes });
    if (!created) {
      showToast("Save failed");
      return false;
    }
    const ok = await deleteInboxItem(item.id);
    if (!ok) showToast("Task saved but inbox not cleared");
    upsertTaskLocal(created);
    await loadInbox();
    showToast("Task added");
    return true;
  });

  const del = makeActionButton("×", "danger", async () => {
    const ok = await deleteInboxItem(item.id);
    if (!ok) {
      showToast("Archive failed");
      return false;
    }
    await loadInbox();
    showUndoToast(`Removed "${truncateLabel(item.text)}"`, async () => {
      const restored = await restoreInboxItem(item.id);
      if (!restored) {
        showToast("Restore failed");
        return;
      }
      await loadInbox();
      showToast("Restored");
    });
    return true;
  });
  del.title = "Archive";

  actions.appendChild(attachBtn);
  actions.appendChild(makeBtn);
  actions.appendChild(del);

  row.appendChild(meta);
  row.appendChild(actions);

  li.appendChild(textDiv);
  li.appendChild(row);
  li.appendChild(pickerHost);
  return li;
}

function buildAttachPicker(inboxItem) {
  const picker = document.createElement("div");
  picker.className = "attach-picker";

  const head = document.createElement("div");
  head.className = "attach-picker-head";
  const headTitle = document.createElement("span");
  headTitle.textContent = "Attach to…";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "attach-picker-close";
  close.title = "Close";
  close.textContent = "×";
  close.addEventListener("click", () => picker.remove());
  head.appendChild(headTitle);
  head.appendChild(close);
  picker.appendChild(head);

  const today = todayKey();
  const scheduledToday = tasks
    .filter((t) => t.schedule && t.schedule.date === today && !t.done)
    .sort((a, b) => a.schedule.startMin - b.schedule.startMin);
  const others = tasks
    .filter(
      (t) =>
        !(t.schedule && t.schedule.date === today) &&
        !t.done &&
        !isSnoozedNow(t),
    )
    .sort((a, b) => b.createdAt - a.createdAt);

  if (scheduledToday.length) {
    picker.appendChild(
      buildAttachSection(
        "On today's timeline",
        scheduledToday.map((t) => ({
          label: t.title,
          sub: `${fmtMin(t.schedule.startMin)}–${fmtMin(t.schedule.startMin + t.schedule.durationMin)}`,
          onPick: () => attachToTask(inboxItem, t.id),
        })),
      ),
    );
  }

  if (others.length) {
    picker.appendChild(
      buildAttachSection(
        "Tasks",
        others.map((t) => ({
          label: t.title,
          sub: scheduleSub(t),
          onPick: () => attachToTask(inboxItem, t.id),
        })),
      ),
    );
  }

  if (!scheduledToday.length && !others.length) {
    const empty = document.createElement("div");
    empty.className = "attach-empty";
    empty.textContent = "No tasks yet. Use Make task instead.";
    picker.appendChild(empty);
  }

  return picker;
}

function scheduleSub(task) {
  if (!task.schedule) return "";
  const d = describeDay(task.schedule.date);
  return `${d} ${fmtMin(task.schedule.startMin)}`;
}

// Human-readable cadence for a task's recurSchedule, e.g. "weekdays at
// 9:00", "every day at 14:30", or "Mon, Wed at 8:00". Returns "" when the
// task has no recurSchedule. Used for the recur sub-line and tooltips.
const WEEKDAY_SET = ["mon", "tue", "wed", "thu", "fri"];
function describeRecur(task) {
  const rs = task && task.recurSchedule;
  if (!rs) return "";
  const at = `at ${fmtMin(rs.startMin)}`;
  const days = rs.days;
  if (!Array.isArray(days) || days.length === 0) return `every day ${at}`;
  const set = new Set(days);
  const isWeekdays =
    set.size === 5 && WEEKDAY_SET.every((d) => set.has(d));
  if (isWeekdays) return `weekdays ${at}`;
  // Preserve a Mon→Sun reading order regardless of stored order.
  const ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  const labels = ORDER.filter((d) => set.has(d)).map(
    (d) => d.charAt(0).toUpperCase() + d.slice(1),
  );
  return `${labels.join(", ")} ${at}`;
}

function buildAttachSection(title, options) {
  const wrap = document.createElement("div");
  wrap.className = "attach-section";
  const heading = document.createElement("div");
  heading.className = "attach-section-title";
  heading.textContent = title;
  wrap.appendChild(heading);
  for (const opt of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "attach-option";
    const label = document.createElement("span");
    label.textContent = opt.label;
    const sub = document.createElement("span");
    sub.className = "time";
    sub.textContent = opt.sub || "";
    btn.appendChild(label);
    btn.appendChild(sub);
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      await opt.onPick();
    });
    wrap.appendChild(btn);
  }
  return wrap;
}

async function attachToTask(inboxItem, taskId) {
  const task = getTask(taskId);
  if (!task) {
    showToast("Task gone");
    return;
  }
  const newNotes = appendNotes(task.notes, inboxItemAsNote(inboxItem));
  const updated = await patchTaskRecord(taskId, { notes: newNotes });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
  const ok = await deleteInboxItem(inboxItem.id);
  if (!ok) showToast("Attached but inbox not cleared");
  await loadInbox();
  showToast(`Attached to "${truncateLabel(updated.title)}"`);
}

function renderInbox(items) {
  list.innerHTML = "";
  for (const item of items) list.appendChild(renderInboxItem(item));
  countEl.textContent = String(items.length);
  emptyEl.style.display = items.length ? "none" : "";
}

export async function loadInbox() {
  const data = await fetchInbox();
  if (data === null) {
    showToast("Failed to load inbox");
    return;
  }
  renderInbox(data.items || []);
}

// ----- Tasks tab rendering -----

function sortByPriority(items) {
  return items.slice().sort((a, b) => {
    const pa = PRIORITY_ORDER[priorityOf(a)] ?? 1;
    const pb = PRIORITY_ORDER[priorityOf(b)] ?? 1;
    if (pa !== pb) return pa - pb;
    return b.createdAt - a.createdAt;
  });
}

function renderTasksList() {
  // Each task lands in exactly one bucket:
  //   - snoozed (snoozedUntil in the future)             → Snoozed disclosure
  //   - completed non-recurring (isHidableComplete)      → Completed disclosure
  //   - everything else                                  → main list
  // Recurring tasks always show in the main list, even when checked done
  // today, because the recurring affordance is "see status + re-complete
  // tomorrow."
  const snoozed = [];
  const completed = [];
  const live = [];
  for (const t of tasks) {
    if (isSnoozedNow(t)) snoozed.push(t);
    else if (isHidableComplete(t)) completed.push(t);
    else live.push(t);
  }
  snoozed.sort((a, b) => a.snoozedUntil - b.snoozedUntil);
  // Completed: most recently finished first.
  completed.sort((a, b) => (b.completedAt || 0) - (a.completedAt || 0));
  const sortedLive = sortByPriority(live);

  tasksListEl.replaceChildren();
  for (const t of sortedLive) tasksListEl.appendChild(renderTaskRow(t));

  tasksCountEl.textContent = String(tasks.length);
  // Empty state only when there's nothing in any section.
  tasksEmptyEl.style.display = tasks.length ? "none" : "";

  // Snoozed disclosure.
  if (snoozed.length === 0) {
    tasksSnoozedDetailsEl.hidden = true;
    tasksSnoozedListEl.replaceChildren();
  } else {
    tasksSnoozedDetailsEl.hidden = false;
    tasksSnoozedSummaryEl.textContent = `Snoozed (${snoozed.length})`;
    tasksSnoozedListEl.replaceChildren();
    for (const t of snoozed) {
      tasksSnoozedListEl.appendChild(renderTaskRow(t, { snoozedView: true }));
    }
  }

  // Completed disclosure (Tier 2 #6). Sibling pattern to Snoozed; reusing
  // the .snoozed-details class for the dashed separator + summary styling.
  if (completed.length === 0) {
    tasksCompletedDetailsEl.hidden = true;
    tasksCompletedListEl.replaceChildren();
  } else {
    tasksCompletedDetailsEl.hidden = false;
    tasksCompletedSummaryEl.textContent = `Completed (${completed.length})`;
    tasksCompletedListEl.replaceChildren();
    for (const t of completed) {
      tasksCompletedListEl.appendChild(renderTaskRow(t));
    }
  }
}

// Build a single task row using the reserved-slot grid (see styles.css for
// the column definitions). Slots that don't apply for a given task stay
// empty placeholder divs, so the column tracks line up across rows.
//
// Slot order (left-to-right grid columns):
//   .ti-stripe   .ti-arrow   .ti-title   .ti-recurring   .ti-notes
//   .ti-due      .ti-snooze  .ti-actions
//
// `.ti-actions` is a vertical bar mirroring `.ti-arrow`: it contains
// `.ti-done` (top 2/3) and `.ti-del` (bottom 1/3) as a single bordered
// unit, giving the row a symmetric pair of action bars at each edge.
function renderTaskRow(task, opts = {}) {
  const snoozedView = !!opts.snoozedView;

  const li = document.createElement("li");
  li.className = "triage-item";
  if (isDoneToday(task)) li.classList.add("done");
  if (snoozedView) li.classList.add("snoozed");
  li.dataset.id = task.id;
  li.dataset.priority = priorityOf(task);
  if (task.id === selectedTaskId) li.classList.add("selected");

  // .ti-stripe — priority stripe (clickable to cycle).
  li.appendChild(makePriorityStripe(task.id, priorityOf(task)));

  // .ti-arrow — wide left-edge bar showing scheduling direction. Only
  // present in the main list (hidden in the snoozed view — you can't
  // schedule a sleeping task without waking it first).
  const arrow = document.createElement("button");
  arrow.type = "button";
  arrow.className = "ti-slot ti-arrow";
  // "On today" is true for an explicit schedule on today's key OR a sticky
  // projection that lands today (recurSchedule with no real schedule). The
  // remove-branch differs: an explicit schedule clears to null, while a
  // projected block adds today to recurExceptions ("skip today").
  const realToday = !!(task.schedule && task.schedule.date === todayKey());
  const projectedToday =
    !realToday && !!projectedScheduleFor(task, todayKey());
  const onToday = realToday || projectedToday;
  arrow.textContent = onToday ? "›" : "‹";
  arrow.title = onToday
    ? "Remove from today's timeline"
    : "Schedule on today's timeline";
  arrow.dataset.state = onToday ? "scheduled" : "unscheduled";
  if (snoozedView) {
    arrow.disabled = true;
    arrow.style.visibility = "hidden";
  }
  arrow.addEventListener("pointerdown", (e) => e.stopPropagation());
  arrow.addEventListener("click", async (e) => {
    e.stopPropagation();
    arrow.disabled = true;
    try {
      if (realToday) {
        const updated = await patchTaskRecord(task.id, { schedule: null });
        if (!updated) {
          showToast("Save failed");
          return;
        }
        upsertTaskLocal(updated);
      } else if (projectedToday) {
        // Sticky block: skip just today by adding an exception.
        const ex = Array.isArray(task.recurExceptions)
          ? task.recurExceptions.slice()
          : [];
        const key = todayKey();
        if (!ex.includes(key)) ex.push(key);
        const updated = await patchTaskRecord(task.id, {
          recurExceptions: ex,
        });
        if (!updated) {
          showToast("Save failed");
          return;
        }
        upsertTaskLocal(updated);
      } else {
        await scheduleTaskOnToday(task.id);
      }
    } finally {
      arrow.disabled = false;
    }
  });
  li.appendChild(arrow);

  // .ti-title — selecting the task happens via clicking the title slot.
  const titleSlot = document.createElement("div");
  titleSlot.className = "ti-slot ti-title";
  const titleText = document.createElement("div");
  titleText.className = "text";
  titleText.textContent = task.title;
  titleSlot.appendChild(titleText);
  // A small sub-line carries the schedule chip when present (the day +
  // start time, not the × — the arrow handles unschedule now). When the
  // task is scheduled on a past date and isn't done for that day, tag
  // the subline as "rolled-over" so the user sees "this got missed."
  if (task.schedule) {
    const sched = document.createElement("div");
    sched.className = "ti-subline";
    if (isRolledOver(task)) sched.classList.add("ti-rolled-over");
    sched.textContent = scheduleSub(task);
    titleSlot.appendChild(sched);
  }
  // Sticky-recurrence sub-line (Tier 2 #15): when a task carries a
  // recurSchedule, show its cadence + time so the user can see "this lands
  // at 9:00 on weekdays" without opening the popover. Shown alongside any
  // explicit schedule subline (a solidified day still keeps its recur rule).
  if (task.recurSchedule) {
    const rec = document.createElement("div");
    rec.className = "ti-subline ti-recur-sub";
    rec.textContent = "↻ " + describeRecur(task);
    titleSlot.appendChild(rec);
  }
  if (snoozedView && task.snoozedUntil) {
    const wake = document.createElement("div");
    wake.className = "ti-subline ti-wake";
    const wakeDate = new Date(task.snoozedUntil * 1000);
    wake.textContent = `asleep until ${wakeDate.toLocaleString(undefined, {
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    })}`;
    titleSlot.appendChild(wake);
  }
  titleSlot.addEventListener("click", (e) => {
    if (e.target.closest("button") || e.target.closest("a")) return;
    setSelectedTask(task.id);
  });
  li.appendChild(titleSlot);

  // .ti-recurring — chasing-arrow toggle. Always shows ↻; the
  // `data-recurring` attribute drives bright-vs-muted styling, matching
  // how delete sits muted at rest. Click opens the recur popover (Tier 2
  // #15): pick a sticky cadence (every day / weekdays / custom + start
  // time), keep the plain "resets at midnight" recurring flag, or stop
  // repeating entirely. A task counts as recurring (bright ↻) when it
  // carries either the recurring flag or a recurSchedule.
  const recurSlot = document.createElement("button");
  recurSlot.type = "button";
  recurSlot.className = "ti-slot ti-recurring";
  recurSlot.textContent = "↻";
  const isRecurring = !!(task.recurring || task.recurSchedule);
  recurSlot.dataset.recurring = isRecurring ? "true" : "false";
  recurSlot.title = task.recurSchedule
    ? `Recurring (${describeRecur(task)}) — click to change`
    : task.recurring
      ? "Recurring — click to change"
      : "One-shot — click to make recurring";
  recurSlot.addEventListener("pointerdown", (e) => e.stopPropagation());
  recurSlot.addEventListener("click", (e) => {
    e.stopPropagation();
    openRecurPopover(task.id, recurSlot);
  });
  li.appendChild(recurSlot);

  // .ti-notes — notes icon (existing).
  const notesSlot = document.createElement("div");
  notesSlot.className = "ti-slot ti-notes";
  const icon = notesIcon(task);
  if (icon) notesSlot.appendChild(icon);
  li.appendChild(notesSlot);

  // .ti-due — due-date display.
  const dueSlot = document.createElement("div");
  dueSlot.className = "ti-slot ti-due";
  if (task.dueDate) {
    const due = formatDueDate(task.dueDate);
    if (due.text) {
      const due_span = document.createElement("span");
      due_span.className = `due-date due-${due.urgency}`;
      due_span.textContent = due.text;
      dueSlot.appendChild(due_span);
    }
  }
  li.appendChild(dueSlot);

  // .ti-snooze — opens the snooze popover (or "Wake now" in the snoozed view).
  const snoozeSlot = document.createElement("div");
  snoozeSlot.className = "ti-slot ti-snooze";
  if (snoozedView) {
    const wakeBtn = makeActionButton("Wake now", null, async () => {
      const updated = await patchTaskRecord(task.id, { snoozedUntil: null });
      if (!updated) {
        showToast("Save failed");
        return false;
      }
      upsertTaskLocal(updated);
      return true;
    });
    snoozeSlot.appendChild(wakeBtn);
  } else {
    const snoozeBtn = makeActionButton("💤", null, async () => {
      openSnoozePopover(task.id, snoozeBtn);
      return false; // keep enabled — the popover handles its own state
    });
    snoozeBtn.title = "Snooze";
    snoozeSlot.appendChild(snoozeBtn);
  }
  li.appendChild(snoozeSlot);

  // .ti-actions — right-edge bar mirroring .ti-arrow on the left. A single
  // bordered column with two stacked buttons: done on top (flex 2), delete
  // below (flex 1). The bar owns the visible border/radius; the buttons
  // inside are borderless and fill their region.
  const actionsBar = document.createElement("div");
  actionsBar.className = "ti-slot ti-actions";

  // .ti-done — completion toggle. Always renders a check glyph; muted at
  // rest, bright green when actually done (mirrors how the × on the
  // delete is muted at rest and red on hover).
  const doneSlot = document.createElement("div");
  doneSlot.className = "ti-done";
  const displayDone = isDoneToday(task);
  const doneBtn = makeActionButton(
    "✓",
    displayDone ? "done" : null,
    async () => {
      // For recurring tasks, the server refreshes completedAt on every
      // PATCH done:true so the wins counter picks up today's completion
      // even if the underlying done flag was already true. Toggle is
      // based on display state, not raw flag.
      const next = !displayDone;
      const updated = await patchTaskRecord(task.id, { done: next });
      if (!updated) {
        showToast("Save failed");
        return false;
      }
      upsertTaskLocal(updated);
      return true;
    },
  );
  doneBtn.title = displayDone ? "Mark not done" : "Mark done";
  doneSlot.appendChild(doneBtn);
  actionsBar.appendChild(doneSlot);

  // .ti-del — delete, bottom 1/3 of the action bar. Muted at rest;
  // danger-red on hover.
  const delSlot = document.createElement("div");
  delSlot.className = "ti-del";
  const del = makeActionButton("×", "danger", async () => {
    const ok = await deleteTaskRecord(task.id);
    if (!ok) {
      showToast("Delete failed");
      return false;
    }
    removeTaskLocal(task.id);
    showUndoToast(`Deleted "${truncateLabel(task.title)}"`, async () => {
      const restored = await restoreTaskRecord(task.id);
      if (!restored) {
        showToast("Restore failed");
        return;
      }
      upsertTaskLocal(restored);
      showToast("Restored");
    });
    return true;
  });
  del.title = "Delete task";
  delSlot.appendChild(del);
  actionsBar.appendChild(delSlot);

  li.appendChild(actionsBar);

  return li;
}

// ----- Popover positioning (shared by snooze + recur) ----------------

// Place a fixed popover relative to its anchor button. Prefers opening below
// the anchor, but flips above when the menu would overflow the bottom of the
// viewport — the case where a task row sits near the bottom of the screen and
// a tall menu (the recur popover especially) would otherwise be cut off and
// unreachable. Right-aligned to the anchor so it never runs off the right
// edge; the top is clamped so the menu can't sit off the top either. The
// popover must already be in the DOM (so offsetHeight is measurable).
function positionPopover(pop, anchorBtn) {
  const rect = anchorBtn.getBoundingClientRect();
  const gap = 6;
  const margin = 8;
  pop.style.position = "fixed";
  pop.style.right = `${window.innerWidth - rect.right}px`;
  pop.style.zIndex = "200";
  const popH = pop.offsetHeight;
  const fitsBelow = rect.bottom + gap + popH <= window.innerHeight - margin;
  let top;
  if (fitsBelow) {
    top = rect.bottom + gap;
  } else {
    const above = rect.top - gap - popH;
    // Flip above when there's room; otherwise clamp so the whole menu stays
    // on-screen (max-height in CSS keeps it from exceeding the viewport).
    top = above >= margin ? above : Math.max(margin, window.innerHeight - popH - margin);
  }
  pop.style.top = `${top}px`;
}

// ----- Snooze popover ------------------------------------------------

// Single in-flight popover at a time. Anchored to the button that opened
// it. Clicking outside dismisses.
let openSnoozePopoverEl = null;
let openSnoozeOutsideHandler = null;

function closeSnoozePopover() {
  if (openSnoozePopoverEl) openSnoozePopoverEl.remove();
  openSnoozePopoverEl = null;
  if (openSnoozeOutsideHandler) {
    document.removeEventListener("pointerdown", openSnoozeOutsideHandler, true);
    openSnoozeOutsideHandler = null;
  }
}

function openSnoozePopover(taskId, anchorBtn) {
  closeSnoozePopover();

  const pop = document.createElement("div");
  pop.className = "snooze-menu";
  for (const preset of SNOOZE_PRESETS) {
    const opt = document.createElement("button");
    opt.type = "button";
    opt.className = "snooze-option";
    opt.textContent = preset.label;
    opt.addEventListener("click", async () => {
      const until = preset.until(new Date());
      // Snoozing should also free up the task's slot on today's timeline
      // (sending a task to bed shouldn't leave a block sitting in your
      // day where the slot is now reclaimable for something else). If
      // the task was scheduled today, clear schedule in the same PATCH.
      const patch = { snoozedUntil: until };
      if (isScheduledToday(getTask(taskId))) {
        patch.schedule = null;
      }
      const updated = await patchTaskRecord(taskId, patch);
      if (!updated) {
        showToast("Snooze failed");
        return;
      }
      upsertTaskLocal(updated);
      closeSnoozePopover();
    });
    pop.appendChild(opt);
  }
  // Anchor: append to the DOM, then position (flips above when near the
  // bottom edge so the menu is never clipped off-screen).
  document.body.appendChild(pop);
  positionPopover(pop, anchorBtn);

  openSnoozePopoverEl = pop;
  openSnoozeOutsideHandler = (e) => {
    if (pop.contains(e.target) || anchorBtn.contains(e.target)) return;
    closeSnoozePopover();
  };
  // Capture-phase so we run before the click that dismissed the popover
  // might re-open it (defensive).
  document.addEventListener("pointerdown", openSnoozeOutsideHandler, true);
}

// ----- Recur popover (Tier 2 #15) ------------------------------------

// Mirrors the snooze popover lifecycle: one in-flight popover, anchored to
// the ↻ button, dismissed on outside click. Lets the user pick a sticky
// cadence (every day / weekdays / chosen days, all at a chosen start time),
// fall back to plain "resets-at-midnight" recurring with no fixed time, or
// stop repeating entirely.
let openRecurPopoverEl = null;
let openRecurOutsideHandler = null;
const RECUR_DEFAULT_DURATION_MIN = 30;
const WEEKDAY_LABELS = [
  ["mon", "Mon"],
  ["tue", "Tue"],
  ["wed", "Wed"],
  ["thu", "Thu"],
  ["fri", "Fri"],
  ["sat", "Sat"],
  ["sun", "Sun"],
];

function closeRecurPopover() {
  if (openRecurPopoverEl) openRecurPopoverEl.remove();
  openRecurPopoverEl = null;
  if (openRecurOutsideHandler) {
    document.removeEventListener("pointerdown", openRecurOutsideHandler, true);
    openRecurOutsideHandler = null;
  }
}

function minToTimeInput(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function timeInputToMin(value) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value || "");
  if (!m) return null;
  const min = Number(m[1]) * 60 + Number(m[2]);
  if (min < 0 || min > 24 * 60) return null;
  return min;
}

function openRecurPopover(taskId, anchorBtn) {
  closeRecurPopover();
  const task = getTask(taskId);
  if (!task) return;

  const rs = task.recurSchedule;
  const durationMin = rs && rs.durationMin ? rs.durationMin : RECUR_DEFAULT_DURATION_MIN;

  const pop = document.createElement("div");
  pop.className = "recur-menu";

  // Start-time input. Seed from the existing recurSchedule, else 9:00.
  const timeRow = document.createElement("label");
  timeRow.className = "recur-time-row";
  const timeLabel = document.createElement("span");
  timeLabel.textContent = "Lands at";
  const timeInput = document.createElement("input");
  timeInput.type = "time";
  timeInput.className = "recur-time-input";
  timeInput.value = minToTimeInput(rs ? rs.startMin : 9 * 60);
  timeRow.appendChild(timeLabel);
  timeRow.appendChild(timeInput);
  pop.appendChild(timeRow);

  // Weekday chips for the "selected days" cadence. Seeded from the existing
  // days (if the task already has a custom set).
  const chipRow = document.createElement("div");
  chipRow.className = "recur-chips";
  const selected = new Set(
    rs && Array.isArray(rs.days) ? rs.days : [],
  );
  for (const [token, label] of WEEKDAY_LABELS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "recur-chip";
    chip.textContent = label;
    chip.dataset.on = selected.has(token) ? "true" : "false";
    chip.addEventListener("click", () => {
      const on = chip.dataset.on === "true";
      chip.dataset.on = on ? "false" : "true";
    });
    chipRow.appendChild(chip);
  }
  pop.appendChild(chipRow);

  const applySchedule = async (days) => {
    const startMin = timeInputToMin(timeInput.value);
    if (startMin === null) {
      showToast("Enter a valid time");
      return;
    }
    const updated = await patchTaskRecord(taskId, {
      recurring: true,
      recurSchedule: { startMin, durationMin, days: days || null },
    });
    if (!updated) {
      showToast("Save failed");
      return;
    }
    upsertTaskLocal(updated);
    closeRecurPopover();
  };

  const addOption = (label, onClick, variant) => {
    const opt = document.createElement("button");
    opt.type = "button";
    opt.className = "recur-option" + (variant ? ` ${variant}` : "");
    opt.textContent = label;
    opt.addEventListener("click", onClick);
    pop.appendChild(opt);
    return opt;
  };

  addOption("Every day", () => applySchedule(null));
  addOption("Weekdays", () => applySchedule(["mon", "tue", "wed", "thu", "fri"]));
  addOption("Selected days", () => {
    const chosen = [];
    chipRow.querySelectorAll(".recur-chip").forEach((c, i) => {
      if (c.dataset.on === "true") chosen.push(WEEKDAY_LABELS[i][0]);
    });
    if (chosen.length === 0) {
      showToast("Pick at least one day");
      return;
    }
    applySchedule(chosen);
  });

  const divider = document.createElement("div");
  divider.className = "recur-divider";
  pop.appendChild(divider);

  // Plain recurring (no fixed time): resets at midnight, stays on the list.
  addOption("Daily, no set time", async () => {
    const updated = await patchTaskRecord(taskId, {
      recurring: true,
      recurSchedule: null,
    });
    if (!updated) {
      showToast("Save failed");
      return;
    }
    upsertTaskLocal(updated);
    closeRecurPopover();
  });

  // Stop repeating: drop both the flag and any sticky schedule.
  if (task.recurring || task.recurSchedule) {
    addOption(
      "Stop repeating",
      async () => {
        const updated = await patchTaskRecord(taskId, {
          recurring: false,
          recurSchedule: null,
        });
        if (!updated) {
          showToast("Save failed");
          return;
        }
        upsertTaskLocal(updated);
        closeRecurPopover();
      },
      "danger",
    );
  }

  document.body.appendChild(pop);
  positionPopover(pop, anchorBtn);

  openRecurPopoverEl = pop;
  openRecurOutsideHandler = (e) => {
    if (pop.contains(e.target) || anchorBtn.contains(e.target)) return;
    closeRecurPopover();
  };
  document.addEventListener("pointerdown", openRecurOutsideHandler, true);
}

// Inline Inbox capture bar — mirrors initTaskForm but posts to /api/inbox.
// Gives a touch-only (keyboard-free) path to quick-capture, since the `\n`
// slash-command modal is unreachable on a phone.
export function initInboxForm() {
  inboxForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = inboxInputEl.value.trim();
    if (!text) return;
    inboxInputEl.value = "";
    const ok = await submitCapture(text);
    if (ok) {
      await loadInbox();
      // Blur on success so a follow-up `\n` / `\t` slash-command keystroke
      // routes to the document rather than this still-focused input.
      inboxInputEl.blur();
    } else {
      inboxInputEl.value = text;
      showToast("Capture failed");
      inboxInputEl.focus();
    }
  });
}

export function initTaskForm() {
  taskForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = taskInputEl.value.trim();
    if (!title) return;
    taskInputEl.value = "";
    const created = await createTaskRecord({ title });
    if (created) {
      upsertTaskLocal(created);
      // Blur on success so a follow-up `\n` / `\t` slash-command keystroke
      // is routed to the document instead of being swallowed by the still-
      // focused inline input. The user can re-click the input to add more
      // via this affordance, but the keyboard-first path is `\t`.
      taskInputEl.blur();
    } else {
      taskInputEl.value = title;
      showToast("Add failed");
      // On failure keep focus so the user can fix and retry without
      // re-clicking the input.
      taskInputEl.focus();
    }
  });
}

// Tasks-tab list refreshes on any task mutation. DAY_CHANGED is included so
// the initial setTasks() bulk-load (and explicit date switches) also paint
// the tasks list, even though the list itself is day-agnostic.
for (const ev of [
  EVENTS.TASK_CREATED,
  EVENTS.TASK_CHANGED,
  EVENTS.TASK_DELETED,
  EVENTS.DAY_CHANGED,
]) {
  bus.on(ev, renderTasksList);
}
