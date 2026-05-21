// Header wins counter. Two sibling elements in the topbar's right column:
//   • #wins-stars — a pile of ⭐ stars, one per **high-priority** completion.
//     Medium and low completions earn no star; the priority signal stays
//     honest. Grows downward as the day fills up.
//   • #wins — the total `✓ N today` count, single-line pill. Every completed
//     task feeds it regardless of priority. Uses the server-stamped
//     `completedAt` (Phase 4.7 A2) so wall-clock yesterday's completions
//     don't carry over.
//
// Layout note: the two elements live side-by-side in `.topbar-right`. The
// count baselines with the **top** row of stars, so its vertical position
// is stable while stars grow underneath.
//
// Star layout: 5 per row, up to 3 visible rows (15 stars). Past 15, the
// final row gets a `+N` overflow indicator.

import { winsEl, winsStarsEl } from "./dom.js";
import { tasks, priorityOf } from "./state.js";
import { bus, EVENTS } from "./events.js";

const STAR = "⭐";
const STARS_PER_ROW = 5;
const MAX_VISIBLE_ROWS = 3;
const MAX_VISIBLE_STARS = STARS_PER_ROW * MAX_VISIBLE_ROWS; // 15

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
  // 0 highs → element stays empty. Right column collapses to just the
  // count pill on the typical empty-day case.
  if (highCount <= 0) return;

  const visible = Math.min(highCount, MAX_VISIBLE_STARS);
  const fullRows = Math.floor(visible / STARS_PER_ROW);
  const lastRowStars = visible % STARS_PER_ROW;
  const overflow = highCount - MAX_VISIBLE_STARS;

  for (let i = 0; i < fullRows; i++) {
    const row = document.createElement("div");
    row.className = "wins-row";
    row.textContent = STAR.repeat(STARS_PER_ROW);
    // Hang the overflow indicator on the bottom-most full row when we hit
    // the cap. A "+N" tag sits on the same line as the 15th star.
    if (i === MAX_VISIBLE_ROWS - 1 && overflow > 0) {
      const tag = document.createElement("span");
      tag.className = "wins-overflow";
      tag.textContent = `+${overflow}`;
      row.appendChild(tag);
    }
    winsStarsEl.appendChild(row);
  }
  if (lastRowStars > 0) {
    const row = document.createElement("div");
    row.className = "wins-row";
    row.textContent = STAR.repeat(lastRowStars);
    winsStarsEl.appendChild(row);
  }
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
