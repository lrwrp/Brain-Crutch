// Notes editor pane — source-only. Opens via:
//   - The [Edit] button inside the notes reader
//   - Pressing `e` on the selected task (works even on tasks with no notes,
//     so this is also the "start writing notes" affordance)
//
// Layout: single full-width textarea that scrolls when the content grows
// past the viewport. No live preview here — the read modal handles
// formatting verification.
//
// Keybindings match the capture modal: Enter saves, Shift+Enter inserts a
// newline, Escape cancels. Save → PATCH the task's notes; the bus's
// TASK_CHANGED event flips the 📝 indicator across renderers. After save
// the task remains selected so follow-up r/e/WASD work without re-clicking.

import {
  notesModalEl,
  notesModalTaskTitleEl,
  notesModalInputEl,
} from "./dom.js";
import { getTask, upsertTaskLocal } from "./state.js";
import { patchTaskRecord } from "./api.js";
import { showToast } from "./toast.js";

let activeTaskId = null;
let originalNotes = "";

export function isNotesEditorOpen() {
  return !notesModalEl.classList.contains("hidden");
}

export function openNotesEditor(taskId) {
  const task = getTask(taskId);
  if (!task) {
    showToast("Task gone");
    return;
  }
  activeTaskId = taskId;
  originalNotes = task.notes || "";
  notesModalTaskTitleEl.textContent = task.title;
  notesModalInputEl.value = originalNotes;
  notesModalEl.classList.remove("hidden");
  // Defer focus past the show transition so the cursor doesn't get clobbered.
  requestAnimationFrame(() => {
    notesModalInputEl.focus();
    const end = notesModalInputEl.value.length;
    notesModalInputEl.setSelectionRange(end, end);
  });
}

export function closeNotesEditor() {
  notesModalEl.classList.add("hidden");
  activeTaskId = null;
  originalNotes = "";
}

async function commit() {
  if (!activeTaskId) {
    closeNotesEditor();
    return;
  }
  const next = notesModalInputEl.value;
  if (next === originalNotes) {
    closeNotesEditor();
    return;
  }
  const cleaned = next.trim();
  const updated = await patchTaskRecord(activeTaskId, {
    notes: cleaned || null,
  });
  if (!updated) {
    showToast("Save failed");
    return;
  }
  upsertTaskLocal(updated);
  showToast("Notes saved");
  closeNotesEditor();
}

export function initNotesEditor() {
  notesModalInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeNotesEditor();
    }
  });
  document.querySelectorAll("[data-notes-close]").forEach((el) => {
    el.addEventListener("click", () => closeNotesEditor());
  });
}
