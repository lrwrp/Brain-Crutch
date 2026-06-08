// Global keyboard handling: Escape (modal/picker/selection), backslash-armed
// slash commands (`\n` inbox, `\t` task), `t` Today shortcut, and WASD on the
// selected task. Also closes selection when the user clicks outside any task.

import {
  tasks,
  selectedTaskId,
  getTask,
  upsertTaskLocal,
  priorityOf,
  shiftPriority,
  clearSelection,
} from "./state.js";
import { patchTaskRecord } from "./api.js";
import { SNAP_MIN, nearestFreeSlot, todayKey } from "./time.js";
import { showToast } from "./toast.js";
import { openCaptureModal, closeCaptureModal, isModalOpen } from "./modal.js";
import { closeNotesEditor, isNotesEditorOpen, openNotesEditor } from "./notes.js";
import {
  closeNotesReader,
  editFromReader,
  isNotesReaderOpen,
  openNotesReader,
} from "./notes-read.js";
import {
  cancelFocus,
  isFocusActive,
  openLauncher,
  handleFocusKey,
} from "./focus.js";
import { stepTaskDuration } from "./triage.js";
import {
  isQueueActive,
  openQueue,
  closeQueue,
  handleQueueKey,
} from "./queue.js";
import { setDate } from "./main.js";

let slashActive = false;
let slashTimer = null;

function isInField(t) {
  return (
    t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)
  );
}

async function moveSelectedTaskBy(deltaMin) {
  if (!selectedTaskId) return;
  const rec = getTask(selectedTaskId);
  if (!rec || !rec.schedule) {
    showToast("Schedule a task first to move it");
    return;
  }
  // Slide-past for W/S: directional search so a blocked nudge skips past the
  // obstacle in the direction the user pressed, rather than no-op'ing or
  // jumping the wrong way.
  const proposed = rec.schedule.startMin + deltaMin;
  const direction = Math.sign(deltaMin); // -1 W, +1 S
  const sameDayOthers = tasks
    .filter(
      (t) =>
        t.id !== rec.id && t.schedule && t.schedule.date === rec.schedule.date,
    )
    .map((t) => ({
      startMin: t.schedule.startMin,
      durationMin: t.schedule.durationMin,
    }));
  const target = nearestFreeSlot(
    sameDayOthers,
    proposed,
    rec.schedule.durationMin,
    { direction },
  );
  if (target === null || target === rec.schedule.startMin) return;
  const updated = await patchTaskRecord(rec.id, {
    schedule: { ...rec.schedule, startMin: target },
  });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
}

async function toggleSelectedDone() {
  if (!selectedTaskId) return;
  const rec = getTask(selectedTaskId);
  if (!rec) return;
  const updated = await patchTaskRecord(rec.id, { done: !rec.done });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
}

async function bumpSelectedPriority(delta) {
  if (!selectedTaskId) return;
  const rec = getTask(selectedTaskId);
  if (!rec) return;
  const next = shiftPriority(priorityOf(rec), delta);
  if (next === priorityOf(rec)) return;
  const updated = await patchTaskRecord(rec.id, { priority: next });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
}

export function initKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      // Pop exactly one layer, topmost first. The notes overlays (z 120) sit
      // ABOVE the queue/focus overlays (z 100), so they close before the queue —
      // e.g. queue → read → Esc returns to the queue, queue → read → edit → Esc
      // returns to read, then Esc again to the queue.
      if (isNotesEditorOpen()) {
        e.preventDefault();
        closeNotesEditor();
        return;
      }
      if (isNotesReaderOpen()) {
        e.preventDefault();
        closeNotesReader();
        return;
      }
      if (isQueueActive()) {
        e.preventDefault();
        closeQueue();
        return;
      }
      if (isFocusActive()) {
        e.preventDefault();
        cancelFocus();
        return;
      }
      if (isModalOpen()) {
        e.preventDefault();
        closeCaptureModal();
        return;
      }
      const hosts = document.querySelectorAll(".picker-host");
      let closed = false;
      hosts.forEach((h) => {
        if (h.firstChild) {
          h.replaceChildren();
          closed = true;
        }
      });
      if (closed) {
        e.preventDefault();
        return;
      }
      if (selectedTaskId) {
        e.preventDefault();
        clearSelection();
        return;
      }
    }

    // Notes overlays sit on top of everything (including the queue), so they
    // take precedence over the queue's key routing below. The editor textarea
    // owns its own typing (Enter saves / Shift+Enter newline via notes.js), so
    // here we just let keys through to it. The reader's only key is `e` → edit
    // (the keyboard twin of its [Edit] button); editFromReader uses the
    // reader's own activeTaskId, so it works even when opened by 📝 click.
    if (isNotesEditorOpen()) return;
    if (isNotesReaderOpen()) {
      if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        editFromReader();
      }
      return;
    }

    // The focus queue overlay owns its own keys (c complete / s skip / r/e
    // notes / Enter) and swallows everything else while it's up. Esc + the
    // notes overlays are handled above.
    if (isQueueActive()) {
      handleQueueKey(e);
      return;
    }

    // Capture modal owns its keys. The focus overlay routes to its bound-task
    // handler (c complete / s snooze / r·e notes when a task is bound) and
    // swallows everything else while it's up.
    if (isModalOpen()) return;
    if (isFocusActive()) {
      handleFocusKey(e);
      return;
    }

    const t = e.target;
    if (isInField(t)) return;

    // Slash-command handling: `\` arms; the next key fires the action.
    // Backslash avoids the browser's Quick Find shortcut on `/`.
    if (slashActive) {
      clearTimeout(slashTimer);
      slashActive = false;
      if (e.key === "n") {
        e.preventDefault();
        openCaptureModal("inbox");
        return;
      }
      if (e.key === "t") {
        e.preventDefault();
        openCaptureModal("task");
        return;
      }
      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        openLauncher();
        return;
      }
      if (e.key === "q" || e.key === "Q") {
        e.preventDefault();
        openQueue();
        return;
      }
      // Unrecognized — drop out and let the key behave normally.
    }
    if (e.key === "\\") {
      e.preventDefault();
      slashActive = true;
      clearTimeout(slashTimer);
      slashTimer = setTimeout(() => {
        slashActive = false;
      }, 1500);
      return;
    }

    if (e.key === "t") {
      e.preventDefault();
      setDate(todayKey());
      return;
    }

    // WASD + r/e only when a task is selected.
    if (selectedTaskId) {
      if (e.key === "w" || e.key === "W") {
        e.preventDefault();
        moveSelectedTaskBy(-SNAP_MIN);
        return;
      }
      if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        moveSelectedTaskBy(SNAP_MIN);
        return;
      }
      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        bumpSelectedPriority(-1);
        return;
      }
      if (e.key === "d" || e.key === "D") {
        e.preventDefault();
        bumpSelectedPriority(1);
        return;
      }
      if (e.key === "l" || e.key === "L") {
        e.preventDefault();
        stepTaskDuration(selectedTaskId, -1); // Less time
        return;
      }
      if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        stepTaskDuration(selectedTaskId, 1); // More time
        return;
      }
      if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        // openNotesReader shows a toast if there are no notes yet.
        openNotesReader(selectedTaskId);
        return;
      }
      if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        // openNotesEditor works on empty notes too — this is also the
        // "start writing notes" affordance for tasks that have none.
        openNotesEditor(selectedTaskId);
        return;
      }
      if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        toggleSelectedDone();
        return;
      }
    }
  });

  // Clicking the empty timeline area or inbox area clears selection.
  document.addEventListener("click", (e) => {
    if (!selectedTaskId) return;
    if (e.target.closest(".task-block") || e.target.closest(".triage-item")) return;
    if (e.target.closest(".attach-picker") || e.target.closest(".modal")) return;
    clearSelection();
  });
}
