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
  taskForm,
  taskInputEl,
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
} from "./state.js";
import {
  fetchInbox,
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
  // Snoozed tasks live in their own collapsible section at the bottom of
  // the Tasks tab; everything else fills the main list. Sort the main list
  // by priority desc then createdAt desc (existing rule).
  const live = tasks.filter((t) => !isSnoozedNow(t));
  const snoozed = tasks
    .filter(isSnoozedNow)
    .sort((a, b) => a.snoozedUntil - b.snoozedUntil);
  const sortedLive = sortByPriority(live);

  tasksListEl.replaceChildren();
  for (const t of sortedLive) tasksListEl.appendChild(renderTaskRow(t));

  tasksCountEl.textContent = String(tasks.length);
  // Empty state only when there's nothing in either section.
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
  const onToday = task.schedule && task.schedule.date === todayKey();
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
      if (onToday) {
        const updated = await patchTaskRecord(task.id, { schedule: null });
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
  // start time, not the × — the arrow handles unschedule now).
  if (task.schedule) {
    const sched = document.createElement("div");
    sched.className = "ti-subline";
    sched.textContent = scheduleSub(task);
    titleSlot.appendChild(sched);
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
  // how delete sits muted at rest. Click toggles the flag (when on, the
  // task stays visible after being checked done and resets the next
  // local day; see state.js#isDoneToday).
  const recurSlot = document.createElement("button");
  recurSlot.type = "button";
  recurSlot.className = "ti-slot ti-recurring";
  recurSlot.textContent = "↻";
  recurSlot.dataset.recurring = task.recurring ? "true" : "false";
  recurSlot.title = task.recurring
    ? "Recurring — click to make one-shot"
    : "One-shot — click to make recurring";
  recurSlot.addEventListener("pointerdown", (e) => e.stopPropagation());
  recurSlot.addEventListener("click", async (e) => {
    e.stopPropagation();
    recurSlot.disabled = true;
    try {
      const updated = await patchTaskRecord(task.id, {
        recurring: !task.recurring,
      });
      if (!updated) {
        showToast("Save failed");
        return;
      }
      upsertTaskLocal(updated);
    } finally {
      recurSlot.disabled = false;
    }
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
  // Anchor: append after the button's row, then position via inline style
  // relative to the anchor's viewport rect.
  document.body.appendChild(pop);
  const rect = anchorBtn.getBoundingClientRect();
  pop.style.position = "fixed";
  pop.style.top = `${rect.bottom + 6}px`;
  // Right-align so the menu doesn't overflow off-screen on narrow viewports.
  pop.style.right = `${window.innerWidth - rect.right}px`;
  pop.style.zIndex = "200";

  openSnoozePopoverEl = pop;
  openSnoozeOutsideHandler = (e) => {
    if (pop.contains(e.target) || anchorBtn.contains(e.target)) return;
    closeSnoozePopover();
  };
  // Capture-phase so we run before the click that dismissed the popover
  // might re-open it (defensive).
  document.addEventListener("pointerdown", openSnoozeOutsideHandler, true);
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
