// Boot orchestrator. Wires DOM event listeners that don't belong to a single
// renderer, kicks off the initial fetches, and starts the clock tick. Every
// other module exports its own ``init*`` and gets called from here.

import {
  clockEl,
  dateEl,
  datePicker,
  datePrevBtn,
  dateNextBtn,
  todayBtn,
  dayHeadingEl,
} from "./dom.js";
import {
  TIME_FMT,
  DATE_FMT,
  todayKey,
  describeDay,
} from "./time.js";
import {
  currentDate,
  setCurrentDate,
  setTasks,
} from "./state.js";
import { fetchTasks } from "./api.js";
import { showToast } from "./toast.js";
import { initTabs, initTaskForm, loadInbox } from "./triage.js";
import { initTimeline } from "./timeline.js";
import { initModal } from "./modal.js";
import { initNotesEditor } from "./notes.js";
import { initNotesReader } from "./notes-read.js";
import { initWinsCounter } from "./wins.js";
import { initCalendarOverlay } from "./calendar.js";
import { initFocusTimer } from "./focus.js";
import { initKeyboard } from "./keyboard.js";

function tickClock() {
  const now = new Date();
  clockEl.textContent = TIME_FMT.format(now);
  dateEl.textContent = DATE_FMT.format(now);
}

export function setDate(d) {
  // setCurrentDate emits DAY_CHANGED; renderers refresh through the bus.
  // We just sync the two header UI controls that aren't subscribers.
  setCurrentDate(d);
  dayHeadingEl.textContent = describeDay(d);
  datePicker.value = d;
}

async function loadTasks() {
  const data = await fetchTasks();
  if (data === null) {
    showToast("Failed to load tasks");
    return;
  }
  setTasks(data.items || []);
}

// Add `days` calendar days to a YYYY-MM-DD key. UTC arithmetic so DST
// boundaries don't drift the result; the input/output are still treated as
// local calendar days everywhere else.
function addDays(dateKey, days) {
  const [y, m, d] = dateKey.split("-").map(Number);
  const utc = Date.UTC(y, m - 1, d) + days * 86400000;
  const dt = new Date(utc);
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(dt.getUTCDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function initDatePicker() {
  datePicker.addEventListener("change", () => {
    if (!datePicker.value) return;
    setDate(datePicker.value);
  });
  todayBtn.addEventListener("click", () => setDate(todayKey()));
  datePrevBtn.addEventListener("click", () => setDate(addDays(currentDate, -1)));
  dateNextBtn.addEventListener("click", () => setDate(addDays(currentDate, 1)));
  dayHeadingEl.textContent = describeDay(currentDate);
  datePicker.value = currentDate;
}

// ----- Boot -----

initTabs();
initTaskForm();
initTimeline();
initModal();
initNotesEditor();
initNotesReader();
initWinsCounter();
initCalendarOverlay();
initFocusTimer();
initKeyboard();
initDatePicker();

tickClock();
setInterval(tickClock, 1000);

loadInbox();
loadTasks();
