// Top-level mobile view switcher. On a phone the .layout grid collapses to a
// single column and only one of {Timeline, Triage} is shown at a time; this
// module owns which one. It sets ``document.body.dataset.mobileView`` and the
// CSS (in the max-width media query) hides the inactive panel.
//
// On desktop the switcher is hidden and the attribute is inert — the
// side-by-side grid shows both panels regardless of its value. Mirrors the
// in-triage ``switchTab`` pattern (active class + localStorage persistence).

import { appViewButtons } from "./dom.js";

const STORAGE_KEY = "app-view";
const DEFAULT_VIEW = "timeline";

export function switchAppView(name) {
  const view = name === "triage" ? "triage" : "timeline";
  document.body.dataset.mobileView = view;
  appViewButtons.forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view),
  );
  try {
    localStorage.setItem(STORAGE_KEY, view);
  } catch {}
}

export function initAppViews() {
  appViewButtons.forEach((b) =>
    b.addEventListener("click", () => switchAppView(b.dataset.view)),
  );
  let saved = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch {}
  switchAppView(saved === "triage" ? "triage" : DEFAULT_VIEW);
}
