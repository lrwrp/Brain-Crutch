// Wins stats modal (Tier 2 #8). Click #wins to open; the modal scans
// `state.tasks` for `done && completedAt` and shows per-window totals,
// priority breakdown, and a current-streak count. Pure client-side —
// no new server endpoint. Subscribes to TASK_* events so re-completing
// while the modal is open redraws live.
//
// Window definitions (rolling):
//   today    midnight local → now
//   week     now − 7 d
//   month    now − 30 d
//   year     now − 365 d
//   all      everything
//
// Below the totals it shows the momentum gauge + activity mosaic (see
// momentum.js) — a forgiving replacement for the old streak counter, which
// reset to zero on any missed day. Momentum decays gently and never "loses".

import {
  statsModal,
  statsTabsEl,
  statsBodyEl,
  winsEl,
  momentumEmberEl,
} from "./dom.js";
import { tasks, priorityOf } from "./state.js";
import { bus, EVENTS } from "./events.js";
import { buildMomentumSection, onActivityChange } from "./momentum.js";

const WINDOWS = [
  { key: "today", label: "Today" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
  { key: "year", label: "Year" },
  { key: "all", label: "All-time" },
];

let activeWindow = "today";
let isOpen = false;

// ----- Date helpers -----

function startOfTodayEpochSeconds() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime() / 1000;
}

function cutoffFor(window) {
  const nowMs = Date.now();
  if (window === "today") return startOfTodayEpochSeconds();
  if (window === "week") return (nowMs - 7 * 86400000) / 1000;
  if (window === "month") return (nowMs - 30 * 86400000) / 1000;
  if (window === "year") return (nowMs - 365 * 86400000) / 1000;
  return 0; // all-time
}

// ----- Computations -----

function statsForWindow(window) {
  const cutoff = cutoffFor(window);
  let total = 0;
  let high = 0;
  let medium = 0;
  let low = 0;
  for (const t of tasks) {
    if (!t.done) continue;
    if (typeof t.completedAt !== "number" || t.completedAt < cutoff) continue;
    total += 1;
    const p = priorityOf(t);
    if (p === "high") high += 1;
    else if (p === "low") low += 1;
    else medium += 1;
  }
  return { total, high, medium, low };
}

// ----- Rendering -----

function render() {
  if (!isOpen) return;

  // Tab pills: mark active.
  for (const btn of statsTabsEl.querySelectorAll(".stats-tab")) {
    btn.classList.toggle("active", btn.dataset.window === activeWindow);
  }

  const { total, high, medium, low } = statsForWindow(activeWindow);

  const totalLine = document.createElement("div");
  totalLine.className = "stats-total";
  totalLine.textContent = `✓ ${total} completed`;

  const breakdown = document.createElement("div");
  breakdown.className = "stats-breakdown";
  // Always show all three so the columns stay stable across tabs.
  breakdown.innerHTML =
    `<span class="stats-prio stats-prio-high">⭐ ${high}</span>` +
    `<span class="stats-prio stats-prio-medium">● ${medium}</span>` +
    `<span class="stats-prio stats-prio-low">○ ${low}</span>`;

  // Momentum gauge + mosaic replaces the old streak line. It's a property of
  // the full activity history, not the selected window, so it's the same on
  // every tab.
  const momentum = buildMomentumSection();

  statsBodyEl.replaceChildren(totalLine, breakdown, momentum);
}

// ----- Open / close -----

export function openStatsModal() {
  isOpen = true;
  statsModal.classList.remove("hidden");
  render();
  // Move keyboard focus into the active tab so Esc + arrow keys work
  // without requiring an extra click.
  const activeBtn = statsTabsEl.querySelector(
    `.stats-tab[data-window="${activeWindow}"]`,
  );
  if (activeBtn) activeBtn.focus();
}

function closeStatsModal() {
  isOpen = false;
  statsModal.classList.add("hidden");
}

// ----- Wiring -----

export function initStatsModal() {
  // Click #wins (or the topbar momentum ember) to open. Both get a
  // cursor: pointer rule in styles.css so the affordance reads visually.
  winsEl.addEventListener("click", openStatsModal);
  if (momentumEmberEl) momentumEmberEl.addEventListener("click", openStatsModal);

  // Re-render the gauge/mosaic live when activity changes while the modal
  // is open (a completion just bumped today's count).
  onActivityChange(() => {
    if (isOpen) render();
  });

  // Tab clicks.
  statsTabsEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".stats-tab");
    if (!btn) return;
    activeWindow = btn.dataset.window;
    render();
  });

  // Backdrop click closes.
  for (const el of statsModal.querySelectorAll("[data-stats-close]")) {
    el.addEventListener("click", closeStatsModal);
  }

  // Esc to close. Scoped via a document handler that only acts when the
  // modal is open — same pattern as the snooze popover / focus launcher.
  document.addEventListener("keydown", (e) => {
    if (!isOpen) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeStatsModal();
    }
  });

  // Live re-render on any task mutation so a completion landed while
  // the modal is open updates the visible numbers.
  for (const ev of [
    EVENTS.TASK_CREATED,
    EVENTS.TASK_CHANGED,
    EVENTS.TASK_DELETED,
    EVENTS.DAY_CHANGED,
  ]) {
    bus.on(ev, render);
  }
}
