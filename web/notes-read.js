// Notes read modal. Renders sanitized Markdown for the task's notes, with an
// [Edit] button that hands off to the editor for the same task. Opened via:
//   - Clicking 📝 (set up in triage.js notesIcon)
//   - Pressing `r` on the selected task (keyboard.js)
//
// Why separate from the editor: the C2 single-modal "source + preview" layout
// caused duplicate display and pushed the preview off-screen on long notes.
// Splitting read and edit lets each scroll independently and lets the read
// path stay lightweight.

import {
  notesReadModalEl,
  notesReadTaskTitleEl,
  notesReadBodyEl,
  notesReadEditBtn,
} from "./dom.js";
import { getTask } from "./state.js";
import { showToast } from "./toast.js";
import { renderMarkdown } from "./markdown.js";
import { openNotesEditor } from "./notes.js";

let activeTaskId = null;

export function isNotesReaderOpen() {
  return !notesReadModalEl.classList.contains("hidden");
}

export function openNotesReader(taskId) {
  const task = getTask(taskId);
  if (!task) {
    showToast("Task gone");
    return;
  }
  if (!task.notes) {
    // `r` was pressed on a task that has nothing to show. The icon is gated
    // on .notes so it can't be reached that way; only keyboard.
    showToast("No notes yet — press e to add");
    return;
  }
  activeTaskId = taskId;
  notesReadTaskTitleEl.textContent = task.title;
  // renderMarkdown is the sanitizer; innerHTML is safe because anything
  // outside its allowlist is HTML-escaped at the inline level.
  notesReadBodyEl.innerHTML = renderMarkdown(task.notes);
  notesReadModalEl.classList.remove("hidden");
}

export function closeNotesReader() {
  notesReadModalEl.classList.add("hidden");
  activeTaskId = null;
}

// Close the reader, open the editor for the same task. Used by the [Edit]
// button and the `e` keyboard shortcut while the reader is open.
export function editFromReader() {
  const id = activeTaskId;
  closeNotesReader();
  if (id) openNotesEditor(id);
}

export function initNotesReader() {
  notesReadEditBtn.addEventListener("click", editFromReader);
  document.querySelectorAll("[data-notes-read-close]").forEach((el) => {
    el.addEventListener("click", () => closeNotesReader());
  });
}
