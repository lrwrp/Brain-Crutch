// Momentum gauge + activity mosaic. A forgiving replacement for the old
// streak: an "ember" whose warmth reflects a *decaying* score over recent
// activity. It brightens with use and cools only gradually — it never resets
// to a "lost" state, so missing a day is a gentle dim, not a failure.
//
// Activity is logged server-side per local day (data/activity.json): opening
// the app counts once per day, and each meaningful action (task create /
// complete / edit / schedule, inbox capture) adds intensity. We hold a local
// copy of that {date: count} map, recompute on change, and render:
//   - the always-visible topbar ember (#momentum-ember), and
//   - a gauge + last-~10-weeks mosaic inside the stats modal.

import { momentumEmberEl } from "./dom.js";
import { bus, EVENTS } from "./events.js";
import { fetchActivity, pingActivity } from "./api.js";

// Tunable: 21-day window, daily decay λ (half-life ≈ 4 days), and the score
// thresholds that map to encouragement levels. All intentionally forgiving —
// level 0 is "let's get going", never "you lost it".
const WINDOW_DAYS = 21;
const LAMBDA = 0.85;
const LEVELS = [
  "let's get going", // 0  — score 0
  "warming up", //       1  — score > 0
  "finding a rhythm", // 2  — score ≥ 4
  "on a roll", //        3  — score ≥ 10
  "blazing", //          4  — score ≥ 20
];

let days = {}; // { "YYYY-MM-DD": count }
const listeners = [];

// ----- Date helpers -----

function dayKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function todayKey() {
  return dayKey(new Date());
}

// ----- Momentum math -----

function computeScore() {
  const base = new Date();
  base.setHours(0, 0, 0, 0);
  let score = 0;
  for (let d = 0; d < WINDOW_DAYS; d++) {
    const dt = new Date(base);
    dt.setDate(base.getDate() - d);
    const c = days[dayKey(dt)] || 0;
    score += c * Math.pow(LAMBDA, d);
  }
  return score;
}

function levelFor(score) {
  if (score >= 20) return 4;
  if (score >= 10) return 3;
  if (score >= 4) return 2;
  if (score > 0) return 1;
  return 0;
}

// ----- Rendering -----

function renderEmber() {
  if (!momentumEmberEl) return;
  const lvl = levelFor(computeScore());
  momentumEmberEl.dataset.level = String(lvl);
  const label = `Momentum: ${LEVELS[lvl]}`;
  momentumEmberEl.title = label;
  momentumEmberEl.setAttribute("aria-label", label);
}

function bucket(count) {
  if (count >= 6) return 3;
  if (count >= 3) return 2;
  if (count >= 1) return 1;
  return 0;
}

// Last ~10 weeks as a 7-row (weekday) × N-column (week) grid, column-major to
// match the familiar contribution-graph layout. Empty days are neutral cells,
// never styled as misses.
function buildMosaic() {
  const grid = document.createElement("div");
  grid.className = "momentum-mosaic";

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const startRaw = new Date(today);
  startRaw.setDate(today.getDate() - 69); // 70-day span
  const gridStart = new Date(startRaw);
  gridStart.setDate(startRaw.getDate() - startRaw.getDay()); // back to Sunday

  const msPerDay = 86400000;
  const totalDays = Math.round((today - gridStart) / msPerDay) + 1;
  const cols = Math.ceil(totalDays / 7);

  for (let col = 0; col < cols; col++) {
    for (let row = 0; row < 7; row++) {
      const dt = new Date(gridStart);
      dt.setDate(gridStart.getDate() + col * 7 + row);
      const cell = document.createElement("div");
      cell.className = "mosaic-cell";
      if (dt > today) {
        cell.dataset.level = "future";
      } else {
        const c = days[dayKey(dt)] || 0;
        cell.dataset.level = String(bucket(c));
        cell.title = `${dayKey(dt)}: ${c} ${c === 1 ? "action" : "actions"}`;
      }
      grid.appendChild(cell);
    }
  }
  return grid;
}

// Built fresh each call; the stats modal includes this in its render().
export function buildMomentumSection() {
  const wrap = document.createElement("div");
  wrap.className = "momentum-section";

  const lvl = levelFor(computeScore());
  const gauge = document.createElement("div");
  gauge.className = "momentum-gauge";
  gauge.dataset.level = String(lvl);

  const ember = document.createElement("span");
  ember.className = "momentum-gauge-ember";
  ember.textContent = "🔥";

  const label = document.createElement("span");
  label.className = "momentum-label";
  label.textContent = LEVELS[lvl];

  gauge.append(ember, label);
  wrap.append(gauge, buildMosaic());
  return wrap;
}

// ----- Recording activity -----

function notify() {
  renderEmber();
  for (const fn of listeners) {
    try {
      fn();
    } catch (err) {
      console.error(err);
    }
  }
}

// Register a callback fired whenever the activity data changes (e.g. the stats
// modal re-renders its gauge/mosaic live).
export function onActivityChange(fn) {
  listeners.push(fn);
}

// Trailing-edge debounce: a burst of events (a completion emits TASK_CHANGED +
// TASK_COMPLETED; a drag fires several) collapses to a single +1. Counts are
// intentionally approximate.
let pingTimer = null;
export function recordActivity() {
  if (pingTimer) return;
  pingTimer = setTimeout(async () => {
    pingTimer = null;
    const res = await pingActivity();
    if (res && res.date) {
      days[res.date] = res.count;
      notify();
    }
  }, 400);
}

// Once-per-local-day "I opened the app" check-in, guarded so reloads don't
// inflate the daily open credit. Pings immediately (not debounced) so just
// showing up registers even with no further action.
function checkInOnce() {
  let last = null;
  try {
    last = localStorage.getItem("activity-open");
  } catch {}
  const t = todayKey();
  if (last === t) return;
  try {
    localStorage.setItem("activity-open", t);
  } catch {}
  pingActivity().then((res) => {
    if (res && res.date) {
      days[res.date] = res.count;
      notify();
    }
  });
}

// ----- Wiring -----

export async function initMomentum() {
  for (const ev of [
    EVENTS.TASK_CREATED,
    EVENTS.TASK_CHANGED,
    EVENTS.TASK_COMPLETED,
  ]) {
    bus.on(ev, recordActivity);
  }
  const data = await fetchActivity();
  days = (data && data.days) || {};
  renderEmber();
  checkInOnce();
}
