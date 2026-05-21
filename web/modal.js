// Slash-command capture modal. Three modes:
//   - inbox: capture text to /api/inbox
//   - task:  create an unscheduled task
//   - day-task: create a task AND schedule it on the day open in the timeline

import { modalEl, modalTitleEl, modalInputEl } from "./dom.js";
import {
  upsertTaskLocal,
  tasksScheduledOn,
} from "./state.js";
import { submitCapture, createTaskRecord } from "./api.js";
import {
  DEFAULT_DURATION_MIN,
  findFreeSlotIn,
} from "./time.js";
import { showToast } from "./toast.js";
import { loadInbox } from "./triage.js";

let modalMode = null;
let modalContext = null;

const MODAL_TITLES = {
  inbox: "Capture to Inbox",
  task: "Create Task",
  "day-task": "Add Task to Day",
};
const MODAL_PLACEHOLDERS = {
  inbox: "A thought, a link, a half-formed idea…",
  task: "Title (multi-line with Shift+Enter)…",
  "day-task": "Title — will be placed in the next free slot",
};

export function openCaptureModal(mode, context = null) {
  modalMode = mode;
  modalContext = context;
  modalTitleEl.textContent = MODAL_TITLES[mode] || "Capture";
  modalInputEl.value = "";
  modalInputEl.placeholder = MODAL_PLACEHOLDERS[mode] || "";
  modalEl.classList.remove("hidden");
  requestAnimationFrame(() => {
    modalInputEl.focus();
  });
}

export function closeCaptureModal() {
  modalEl.classList.add("hidden");
  modalMode = null;
  modalContext = null;
}

export function isModalOpen() {
  return !modalEl.classList.contains("hidden");
}

async function commitCaptureModal() {
  const text = modalInputEl.value.trim();
  if (!text) {
    closeCaptureModal();
    return;
  }
  if (modalMode === "inbox") {
    const ok = await submitCapture(text);
    if (!ok) {
      showToast("Capture failed");
      return;
    }
    showToast("Captured");
    closeCaptureModal();
    await loadInbox();
  } else if (modalMode === "task") {
    const created = await createTaskRecord({ title: text });
    if (!created) {
      showToast("Add failed");
      return;
    }
    upsertTaskLocal(created);
    showToast("Task added");
    closeCaptureModal();
  } else if (modalMode === "day-task") {
    const ctx = modalContext;
    // Re-check the slot: tasks may have changed since we opened.
    const slot = findFreeSlotIn(
      tasksScheduledOn(ctx.date),
      ctx.date,
      DEFAULT_DURATION_MIN,
    );
    if (!slot) {
      showToast("No free time left on this day");
      closeCaptureModal();
      return;
    }
    const created = await createTaskRecord({
      title: text,
      schedule: {
        date: ctx.date,
        startMin: slot.startMin,
        durationMin: slot.durationMin,
      },
    });
    if (!created) {
      showToast("Save failed");
      return;
    }
    upsertTaskLocal(created);
    const shrunk = slot.durationMin < DEFAULT_DURATION_MIN;
    showToast(shrunk ? `Added (${slot.durationMin}m — only gap left)` : "Added");
    closeCaptureModal();
  }
}

export function initModal() {
  modalInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      commitCaptureModal();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeCaptureModal();
    }
  });
  document.querySelectorAll("[data-modal-close]").forEach((el) => {
    el.addEventListener("click", () => closeCaptureModal());
  });
}
