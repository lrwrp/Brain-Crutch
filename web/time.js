// Time/date primitives and timeline constants. Pure functions, no DOM, no
// state — safe to import from anywhere.

// Two-window model: the timeline canvas spans the full 24 hours so the user
// can drag late-night / pre-dawn tasks freely, but the *focus* window
// (08:00–20:00) is what `findFreeSlotIn` searches for auto-scheduling
// (+task / Today). Manual drag/resize/W-S use TIMELINE bounds; auto-schedule
// uses FOCUS bounds. Keeping the legacy names (DAY_START/END) on the focus
// pair so existing call sites and tests don't need to rewire.
export const TIMELINE_START_MIN = 0;
export const TIMELINE_END_MIN = 24 * 60;
export const DAY_START_MIN = 8 * 60; // auto-schedule lower bound
export const DAY_END_MIN = 20 * 60; // auto-schedule upper bound
export const PX_PER_MIN = 1;
export const SNAP_MIN = 15;
export const DEFAULT_DURATION_MIN = 30;
export const MIN_DURATION_MIN = 15;

export const TIME_FMT = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
export const DATE_FMT = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  month: "short",
  day: "numeric",
});
export const DATE_FMT_SHORT = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
});

export function todayKey() {
  return dateKey(new Date());
}

export function dateKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseDateKey(key) {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function dayDiff(aKey, bKey) {
  return Math.round((parseDateKey(aKey) - parseDateKey(bKey)) / 86400000);
}

export function describeDay(key) {
  const diff = dayDiff(key, todayKey());
  if (diff === 0) return "Today";
  if (diff === -1) return "Yesterday";
  if (diff === 1) return "Tomorrow";
  return DATE_FMT_SHORT.format(parseDateKey(key));
}

export function nowMinutes() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
}

export function fmtMin(min) {
  const h = Math.floor(min / 60) % 24;
  const m = Math.floor(min % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function snap(min) {
  return Math.round(min / SNAP_MIN) * SNAP_MIN;
}

export function clampStart(startMin, duration) {
  // Drag/resize clamp uses the full 24h canvas so off-hours tasks are
  // possible. Auto-schedule still constrains itself via findFreeSlotIn.
  return Math.max(
    TIMELINE_START_MIN,
    Math.min(startMin, TIMELINE_END_MIN - duration),
  );
}

export function relativeTime(ts) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function truncateLabel(s) {
  if (!s) return "";
  return s.length > 28 ? s.slice(0, 27) + "…" : s;
}

// ----- Due-date display -----

const DUE_WEEKDAY_FMT = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
});
const DUE_MD_FMT = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

// Returns `{text, urgency}` for the row's due-date slot. `urgency` is one of
// "overdue" | "today" | "soon" | "future" | null (for no dueDate).
// Callers map urgency to a CSS class for color. Text styles intentionally
// shift between absolute / relative formats based on closeness:
//   past         → "OVERDUE"      (red)
//   today        → "DUE TODAY"    (red)
//   tomorrow     → "due tomorrow" (yellow)
//   2-6 days out → "due Wed"      (yellow if ≤3 days, muted otherwise)
//   7+ days out  → "due May 27"   (muted)
export function formatDueDate(dueDate) {
  if (!dueDate) return { text: "", urgency: null };
  const today = todayKey();
  const delta = dayDiff(dueDate, today);
  if (delta < 0) return { text: "OVERDUE", urgency: "overdue" };
  if (delta === 0) return { text: "DUE TODAY", urgency: "today" };
  if (delta === 1) return { text: "due tomorrow", urgency: "soon" };
  if (delta <= 6) {
    return {
      text: `due ${DUE_WEEKDAY_FMT.format(parseDateKey(dueDate))}`,
      urgency: delta <= 3 ? "soon" : "future",
    };
  }
  return {
    text: `due ${DUE_MD_FMT.format(parseDateKey(dueDate))}`,
    urgency: "future",
  };
}

// ----- Snooze duration presets -----

// Each preset returns the epoch-seconds wake-up time given the current Date.
// Labels are ADHD-calibrated common cases.
export const SNOOZE_PRESETS = [
  { label: "1 hour", until: (now) => Math.floor(now.getTime() / 1000) + 60 * 60 },
  {
    label: "Until end of day",
    until: (now) => {
      const eod = new Date(now);
      eod.setHours(23, 59, 0, 0);
      return Math.floor(eod.getTime() / 1000);
    },
  },
  {
    label: "Tomorrow morning",
    until: (now) => {
      const t = new Date(now);
      t.setDate(t.getDate() + 1);
      t.setHours(8, 0, 0, 0);
      return Math.floor(t.getTime() / 1000);
    },
  },
  {
    label: "3 days",
    until: (now) => Math.floor(now.getTime() / 1000) + 3 * 86400,
  },
  {
    label: "1 week",
    until: (now) => Math.floor(now.getTime() / 1000) + 7 * 86400,
  },
];

// Given a list of other tasks on the day plus a desired start position +
// duration, return the closest non-overlapping start that fits the day
// window — or null if no slot exists anywhere.
//
// Used by drag-release ("slide past" — snap to nearest free slot when the
// user releases atop another block) and by W/S nudges ("skip past
// obstacles" — search in the nudge direction).
//
// Options:
//   direction: -1, 0, +1
//     0  bidirectional (default). Tries ``desiredStart`` first, then walks
//        outward by SNAP_MIN in both directions, trying forward at each
//        distance before backward.
//     +1 forward-only: starts at desiredStart, walks up (toward DAY_END).
//     -1 backward-only: starts at desiredStart, walks down (toward DAY_START).
//
// `desiredStart` is internally snapped to the SNAP_MIN grid.
export function nearestFreeSlot(otherTasks, desiredStart, duration, opts = {}) {
  const direction = opts.direction ?? 0;
  // Drag-release / W-S slide search uses the full 24h canvas (matches
  // clampStart). Auto-schedule's narrower 08-20 search lives in
  // findFreeSlotIn instead.
  const minStart = TIMELINE_START_MIN;
  const maxStart = TIMELINE_END_MIN - duration;
  if (maxStart < minStart) return null;

  function fits(start) {
    if (start < minStart || start > maxStart) return false;
    const end = start + duration;
    return !otherTasks.some(
      (t) => start < t.startMin + t.durationMin && end > t.startMin,
    );
  }

  const desiredClamped = Math.max(
    minStart,
    Math.min(maxStart, snap(desiredStart)),
  );
  const span = maxStart - minStart;
  const maxSteps = Math.ceil(span / SNAP_MIN);

  if (direction === 0) {
    if (fits(desiredClamped)) return desiredClamped;
    for (let i = 1; i <= maxSteps; i++) {
      const fwd = desiredClamped + i * SNAP_MIN;
      if (fits(fwd)) return fwd;
      const back = desiredClamped - i * SNAP_MIN;
      if (fits(back)) return back;
    }
    return null;
  }
  let cur = desiredClamped;
  for (let i = 0; i <= maxSteps; i++) {
    if (fits(cur)) return cur;
    cur += direction * SNAP_MIN;
    if (cur < minStart || cur > maxStart) return null;
  }
  return null;
}

// Pure slot-search: walks the day window from a sensible start (now if today,
// 08:00 otherwise), skips over each blocker, and returns the first gap that
// fits at least SNAP_MIN minutes (clamped to ``preferredDuration``).
// Returns ``null`` if the day is full.
export function findFreeSlotIn(tasksOnDay, dateStr, preferredDuration) {
  const isToday = dateStr === todayKey();
  let cursor;
  if (isToday) {
    const now = nowMinutes();
    cursor = snap(Math.max(now, DAY_START_MIN));
    if (cursor < now) cursor += SNAP_MIN;
  } else {
    cursor = DAY_START_MIN;
  }
  cursor = Math.max(cursor, DAY_START_MIN);

  const sorted = tasksOnDay.slice().sort((a, b) => a.startMin - b.startMin);

  while (cursor < DAY_END_MIN) {
    const blocker = sorted.find((t) => t.startMin + t.durationMin > cursor);
    const gapEnd = blocker ? blocker.startMin : DAY_END_MIN;
    if (gapEnd > cursor) {
      const available = gapEnd - cursor;
      if (available >= SNAP_MIN) {
        return {
          startMin: cursor,
          durationMin: Math.min(preferredDuration, available),
        };
      }
    }
    if (!blocker) return null;
    cursor = Math.ceil((blocker.startMin + blocker.durationMin) / SNAP_MIN) * SNAP_MIN;
  }
  return null;
}
