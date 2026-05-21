// Bottom-centered toast. Two modes:
//   - showToast(msg): ephemeral, auto-fades after 1.4 s.
//   - showUndoToast(msg, onUndo): persistent; visible until the user clicks
//     [Undo] or × on the toast itself.

import { toast } from "./dom.js";

export function clearToast() {
  clearTimeout(showToast._t);
  showToast._t = null;
  toast.textContent = "";
  toast.classList.remove("show");
}

export function showToast(msg) {
  clearToast();
  toast.textContent = msg;
  toast.classList.add("show");
  showToast._t = setTimeout(() => toast.classList.remove("show"), 1400);
}

export function showUndoToast(message, onUndo) {
  clearToast();
  const text = document.createElement("span");
  text.className = "toast-text";
  text.textContent = message;
  const undoBtn = document.createElement("button");
  undoBtn.type = "button";
  undoBtn.className = "toast-undo";
  undoBtn.textContent = "Undo";
  undoBtn.addEventListener("click", async () => {
    clearToast();
    try {
      await onUndo();
    } catch (err) {
      console.error("undo failed", err);
      showToast("Restore failed");
    }
  });
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "toast-close";
  closeBtn.setAttribute("aria-label", "Dismiss");
  closeBtn.textContent = "×";
  closeBtn.addEventListener("click", clearToast);
  toast.appendChild(text);
  toast.appendChild(undoBtn);
  toast.appendChild(closeBtn);
  toast.classList.add("show");
}
