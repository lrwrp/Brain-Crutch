// Calendar overlay: read-only external events behind the day timeline.
//
// Two render targets per day:
//   - Timed events become dimmed blocks inside #tracks, pointer-events: none,
//     positioned absolutely the same way task blocks are. Lower z-index so
//     real task blocks sit on top.
//   - All-day events become chips in #all-day-strip, which sits between the
//     timeline-head and the scrollable timeline — so it stays pinned at the
//     top while the user scrolls through the 24-hour canvas.
//
// Refresh triggers: on boot, on every DAY_CHANGED (so date arrows / Today /
// picker repaint the overlay), and on a 60-second timer (so re-exported .ics
// files show up without a manual reload).

import { tracksEl, allDayStripEl } from "./dom.js";
import { currentDate } from "./state.js";
import { bus, EVENTS } from "./events.js";
import { fetchCalendarEvents } from "./api.js";
import { TIMELINE_START_MIN, PX_PER_MIN, fmtMin } from "./time.js";

const REFRESH_INTERVAL_MS = 60 * 1000;

function clearOverlay() {
  for (const el of tracksEl.querySelectorAll(".calendar-event")) el.remove();
  allDayStripEl.replaceChildren();
}

function renderTimedEvent(event) {
  const el = document.createElement("div");
  el.className = "calendar-event";
  el.dataset.source = event.source;
  el.style.top = `${(event.startMin - TIMELINE_START_MIN) * PX_PER_MIN}px`;
  el.style.height = `${(event.endMin - event.startMin) * PX_PER_MIN}px`;

  const summary = document.createElement("div");
  summary.className = "calendar-event-title";
  summary.textContent = event.summary;

  const meta = document.createElement("div");
  meta.className = "calendar-event-time";
  meta.textContent = `${fmtMin(event.startMin)}–${fmtMin(event.endMin)} · ${event.source}`;

  el.appendChild(summary);
  el.appendChild(meta);
  // Tooltip carries the full title even when the block is too short to show
  // the meta line.
  el.title = `${event.summary} (${fmtMin(event.startMin)}–${fmtMin(event.endMin)}, ${event.source})`;
  return el;
}

function renderAllDayChip(event) {
  const chip = document.createElement("span");
  chip.className = "all-day-chip";
  chip.dataset.source = event.source;
  chip.textContent = event.summary;
  chip.title = `${event.summary} (${event.source})`;
  return chip;
}

let inFlightDate = null;

async function loadAndRender() {
  // Snapshot the date we're loading so a late response from a stale fetch
  // (e.g. user clicked next-day while we were still loading) doesn't paint
  // yesterday's events on top of today's.
  const target = currentDate;
  inFlightDate = target;
  const data = await fetchCalendarEvents(target);
  if (data === null || inFlightDate !== target) return;
  clearOverlay();
  for (const event of data.events || []) {
    if (event.allDay) {
      allDayStripEl.appendChild(renderAllDayChip(event));
    } else {
      tracksEl.appendChild(renderTimedEvent(event));
    }
  }
}

export function initCalendarOverlay() {
  bus.on(EVENTS.DAY_CHANGED, loadAndRender);
  setInterval(loadAndRender, REFRESH_INTERVAL_MS);
  // Boot paint — main.js's loadTasks will fire DAY_CHANGED too, but doing
  // an explicit load here means the overlay shows up even if the tasks
  // fetch fails or is slow.
  loadAndRender();
}
