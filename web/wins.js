// Header wins counter.
//   • #wins — the total `✓ N today` count, single-line pill (paired with the
//     Focus button in .topbar-actions). Every completed task feeds it
//     regardless of priority. Uses the server-stamped `completedAt`
//     (Phase 4.7 A2) so wall-clock yesterday's completions don't carry over.
//   • #wins-stars — a single right-aligned row of ⭐, one per **high-priority**
//     completion, sitting beneath the action pills. Medium and low earn no
//     star; the priority signal stays honest.
//
// Star layout: a single row, up to MAX_VISIBLE_STARS; past that a `+N`
// overflow tag closes the row.

import { winsEl, winsStarsEl } from "./dom.js";
import { tasks, priorityOf } from "./state.js";
import { bus, EVENTS } from "./events.js";

const STAR = "⭐";
const MAX_VISIBLE_STARS = 10;

function startOfTodayEpochSeconds() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime() / 1000;
}

function countWinsToday() {
  const cutoff = startOfTodayEpochSeconds();
  let total = 0;
  let high = 0;
  for (const t of tasks) {
    if (!t.done) continue;
    if (typeof t.completedAt !== "number" || t.completedAt < cutoff) continue;
    total += 1;
    if (priorityOf(t) === "high") high += 1;
  }
  return { total, high };
}

function renderStars(highCount) {
  winsStarsEl.replaceChildren();
  // 0 highs → element stays empty and collapses via the :empty CSS rule.
  if (highCount <= 0) return;

  const visible = Math.min(highCount, MAX_VISIBLE_STARS);
  const overflow = highCount - MAX_VISIBLE_STARS;

  const row = document.createElement("div");
  row.className = "wins-row";
  row.textContent = STAR.repeat(visible);
  if (overflow > 0) {
    const tag = document.createElement("span");
    tag.className = "wins-overflow";
    tag.textContent = `+${overflow}`;
    row.appendChild(tag);
  }
  winsStarsEl.appendChild(row);
}

function render() {
  const { total, high } = countWinsToday();
  renderStars(high);

  // #wins is back to a single text node — siblings to #wins-stars now.
  winsEl.textContent = `✓ ${total} today`;

  // Tooltip carries the priority breakdown so a hover answers
  // "yes but how many of those were the important ones?" without opening
  // the (future) stats modal.
  winsEl.title =
    high > 0
      ? `${total} completed today (${high} high-priority)`
      : `${total} completed today`;
}

export function initWinsCounter() {
  // Any mutation can affect the count (create-done, change-done, delete a
  // completed task, switch day). Subscribe broadly; the count is O(tasks)
  // which is fine at the scales we'll ever see locally.
  for (const ev of [
    EVENTS.TASK_CREATED,
    EVENTS.TASK_CHANGED,
    EVENTS.TASK_DELETED,
    EVENTS.DAY_CHANGED,
  ]) {
    bus.on(ev, render);
  }
  // Paint once on boot in case nothing else has fired yet (initial setTasks
  // will fire DAY_CHANGED, but render-on-init is cheap insurance).
  render();
}
