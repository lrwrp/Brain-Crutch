// Focus timer. Self-contained countdown tool — not bound to any task.
//
// State machine:
//   idle      — overlay hidden, launcher hidden
//   launcher  — duration-entry modal open
//   preroll   — overlay shown, "3 → 2 → 1" countdown
//   running   — overlay shown, MM:SS counting down
//   done      — overlay shown, Restart / Close buttons
//
// Transitions:
//   idle      → launcher  (button click / `\f` slash command)
//   launcher  → idle       (Esc / backdrop click)
//   launcher  → preroll    (Enter)
//   preroll   → running    (after 3 seconds of preroll)
//   preroll   → idle       (Esc — cancel before timer starts)
//   running   → done       (timer hits 00:00)
//   running   → idle       (Cancel button / Esc)
//   done      → preroll    (Restart — re-uses last duration)
//   done      → idle       (Close)
//
// The whole module is in-memory: closing the tab destroys the timer. No
// localStorage persistence — KISS for v1.

import {
  focusBtn,
  focusLauncherEl,
  focusMinusBtn,
  focusPlusBtn,
  focusMinutesInput,
  focusOverlayEl,
  focusStatePrerollEl,
  focusStateRunningEl,
  focusStateDoneEl,
  focusPrerollNumEl,
  focusClockEl,
  focusCancelBtn,
  focusRestartBtn,
  focusCloseBtn,
  focusDoneDetailEl,
} from "./dom.js";

const MIN_MINUTES = 1;
const MAX_MINUTES = 45;
const DEFAULT_MINUTES = 5;
// Hold-to-repeat: after a single click, we wait HOLD_THRESHOLD_MS before
// starting to repeat at REPEAT_INTERVAL_MS. The repeat step is ±5 so a held
// press accelerates faster than a click-by-click run-up.
const HOLD_THRESHOLD_MS = 400;
const REPEAT_INTERVAL_MS = 110;
const HOLD_STEP = 5;

let state = "idle";
let lastDuration = DEFAULT_MINUTES; // remembered for Restart
let prerollIndex = 0;
let prerollTimer = null;
let tickTimer = null;
let endAt = 0;

// ----- Helpers ---------------------------------------------------------

function clampMinutes(n) {
  if (!Number.isFinite(n)) return DEFAULT_MINUTES;
  return Math.max(MIN_MINUTES, Math.min(MAX_MINUTES, Math.round(n)));
}

function readMinutes() {
  return clampMinutes(parseInt(focusMinutesInput.value, 10));
}

function setMinutes(n) {
  focusMinutesInput.value = String(clampMinutes(n));
}

function adjustMinutes(delta) {
  setMinutes(readMinutes() + delta);
}

function fmtClock(secondsRemaining) {
  // Always two-digit minutes + seconds. Negative values clamp to 0 so the
  // last tick doesn't briefly read "-00:01".
  const s = Math.max(0, Math.ceil(secondsRemaining));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function showOnlyState(el) {
  for (const e of [focusStatePrerollEl, focusStateRunningEl, focusStateDoneEl]) {
    e.classList.toggle("hidden", e !== el);
  }
}

function stopAllTimers() {
  if (prerollTimer !== null) clearInterval(prerollTimer);
  if (tickTimer !== null) clearInterval(tickTimer);
  prerollTimer = null;
  tickTimer = null;
}

// ----- State transitions ----------------------------------------------

export function isFocusActive() {
  // True whenever the user is in any focus state — used by keyboard.js to
  // gate slash-command handling so `\n` doesn't steal Enter from the
  // launcher, etc.
  return state !== "idle";
}

export function openLauncher() {
  state = "launcher";
  setMinutes(lastDuration);
  focusLauncherEl.classList.remove("hidden");
  requestAnimationFrame(() => {
    focusMinutesInput.focus();
    focusMinutesInput.select();
  });
}

function closeLauncher() {
  focusLauncherEl.classList.add("hidden");
  if (state === "launcher") state = "idle";
}

function startPreroll(minutes) {
  lastDuration = minutes;
  state = "preroll";
  closeLauncher();
  showOnlyState(focusStatePrerollEl);
  focusOverlayEl.classList.remove("hidden");

  // Show 3, 2, 1 in successive seconds, then start the actual timer.
  prerollIndex = 3;
  paintPrerollNum();
  prerollTimer = setInterval(() => {
    prerollIndex -= 1;
    if (prerollIndex <= 0) {
      clearInterval(prerollTimer);
      prerollTimer = null;
      startRunning(minutes);
    } else {
      paintPrerollNum();
    }
  }, 1000);
}

function paintPrerollNum() {
  focusPrerollNumEl.textContent = String(prerollIndex);
  // Restart the pulse animation by toggling the class. Without this the
  // CSS animation only plays once on first paint.
  focusPrerollNumEl.classList.remove("focus-preroll-num");
  void focusPrerollNumEl.offsetWidth; // force reflow
  focusPrerollNumEl.classList.add("focus-preroll-num");
}

function startRunning(minutes) {
  state = "running";
  endAt = Date.now() + minutes * 60 * 1000;
  showOnlyState(focusStateRunningEl);
  paintClock();
  // 250 ms tick so the seconds digit feels responsive. Cheap.
  tickTimer = setInterval(() => {
    if (state !== "running") return;
    const remaining = (endAt - Date.now()) / 1000;
    if (remaining <= 0) {
      clearInterval(tickTimer);
      tickTimer = null;
      enterDone(minutes);
      return;
    }
    paintClock();
  }, 250);
}

function paintClock() {
  const remaining = (endAt - Date.now()) / 1000;
  focusClockEl.textContent = fmtClock(remaining);
}

function enterDone(elapsedMinutes) {
  state = "done";
  focusDoneDetailEl.textContent = `${elapsedMinutes} ${elapsedMinutes === 1 ? "minute" : "minutes"} elapsed.`;
  focusClockEl.textContent = "00:00";
  showOnlyState(focusStateDoneEl);
}

export function cancelFocus() {
  // From any state → back to idle. Hide everything, stop timers.
  stopAllTimers();
  focusOverlayEl.classList.add("hidden");
  closeLauncher();
  state = "idle";
}

function restart() {
  // From done state, re-roll with the same duration.
  if (state !== "done") return;
  startPreroll(lastDuration);
}

// ----- Wiring ----------------------------------------------------------

function attachStepButton(btn, delta) {
  // Click = ±1; press-and-hold (>HOLD_THRESHOLD_MS) = ±HOLD_STEP per
  // REPEAT_INTERVAL_MS until release.
  let holdTimer = null;
  let repeatTimer = null;
  const cleanup = () => {
    if (holdTimer !== null) clearTimeout(holdTimer);
    if (repeatTimer !== null) clearInterval(repeatTimer);
    holdTimer = null;
    repeatTimer = null;
  };
  btn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    adjustMinutes(delta); // immediate single-click increment
    holdTimer = setTimeout(() => {
      repeatTimer = setInterval(() => {
        adjustMinutes(delta * HOLD_STEP);
      }, REPEAT_INTERVAL_MS);
    }, HOLD_THRESHOLD_MS);
  });
  for (const evt of ["pointerup", "pointerleave", "pointercancel"]) {
    btn.addEventListener(evt, cleanup);
  }
}

export function initFocusTimer() {
  focusBtn.addEventListener("click", openLauncher);

  attachStepButton(focusMinusBtn, -1);
  attachStepButton(focusPlusBtn, +1);

  // Clamp on any direct typing.
  focusMinutesInput.addEventListener("change", () => setMinutes(readMinutes()));
  focusMinutesInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      startPreroll(readMinutes());
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelFocus();
    }
  });

  // Launcher backdrop click → cancel.
  document.querySelectorAll("[data-focus-launcher-close]").forEach((el) => {
    el.addEventListener("click", cancelFocus);
  });

  focusCancelBtn.addEventListener("click", cancelFocus);
  focusRestartBtn.addEventListener("click", restart);
  focusCloseBtn.addEventListener("click", cancelFocus);
}
