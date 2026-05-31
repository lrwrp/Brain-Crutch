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
import { cancelFocus, isFocusActive, openLauncher } from "./focus.js";
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

    // The focus queue overlay owns its own keys (c complete / s skip / Enter)
    // and swallows everything else while it's up. Esc is handled above.
    if (isQueueActive()) {
      handleQueueKey(e);
      return;
    }

    // While a modal is open, let it own all keys. The notes reader is special
    // — its only chrome is the [Edit] button, so we want `e` here to behave
    // as the keyboard equivalent of clicking that button. The focus overlay
    // owns its own buttons + Esc; gate global keys behind it too.
    if (isModalOpen() || isNotesEditorOpen() || isFocusActive()) return;
    if (isNotesReaderOpen()) {
      if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        // editFromReader uses the reader's own activeTaskId, so this also
        // works when the reader was opened by 📝 click (which doesn't set
        // selectedTaskId on its own).
        editFromReader();
      }
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
