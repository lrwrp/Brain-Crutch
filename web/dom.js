// DOM element handles, looked up once at module load. All other modules
// import these instead of repeating `document.querySelector` calls.

const $ = (sel) => document.querySelector(sel);

export const clockEl = $("#clock");
export const dateEl = $("#date");
export const dateWeekdayEl = $("#date-weekday");
export const dateMonthDayEl = $("#date-monthday");
export const winsEl = $("#wins");
export const winsStarsEl = $("#wins-stars");
export const momentumEmberEl = $("#momentum-ember");

export const list = $("#inbox-list");
export const countEl = $("#inbox-count");
export const emptyEl = $("#inbox-empty");
export const inboxForm = $("#inbox-form");
export const inboxInputEl = $("#inbox-input");

export const toast = $("#toast");

export const timelineEl = $("#timeline");
export const hoursEl = $("#hours");
export const tracksEl = $("#tracks");
export const nowLineEl = $("#now-line");
export const nowPillEl = $("#now-pill");
export const allDayStripEl = $("#all-day-strip");

export const addBtn = $("#add-task");
export const todayBtn = $("#today-btn");
export const datePicker = $("#date-picker");
export const datePrevBtn = $("#date-prev");
export const dateNextBtn = $("#date-next");
export const dayHeadingEl = $("#day-heading");

export const tabButtons = document.querySelectorAll(".tab");
export const tabPanels = document.querySelectorAll(".tab-panel");

// Top-level mobile view switcher (Timeline / Triage). Hidden on desktop via
// CSS; the buttons toggle body[data-mobile-view].
export const appViewButtons = document.querySelectorAll(".app-view");

export const taskForm = $("#task-form");
export const taskInputEl = $("#task-input");
export const tasksCountEl = $("#tasks-count");
export const tasksListEl = $("#tasks-list");
export const tasksEmptyEl = $("#tasks-empty");
export const tasksSnoozedDetailsEl = $("#tasks-snoozed-details");
export const tasksSnoozedSummaryEl = $("#tasks-snoozed-summary");
export const tasksSnoozedListEl = $("#tasks-snoozed-list");
export const tasksCompletedDetailsEl = $("#tasks-completed-details");
export const tasksCompletedSummaryEl = $("#tasks-completed-summary");
export const tasksCompletedListEl = $("#tasks-completed-list");

export const statsModal = $("#stats-modal");
export const statsTabsEl = $("#stats-tabs");
export const statsBodyEl = $("#stats-body");

export const modalEl = $("#capture-modal");
export const modalTitleEl = $("#capture-modal-title");
export const modalInputEl = $("#capture-modal-input");

export const notesModalEl = $("#notes-modal");
export const notesModalTaskTitleEl = $("#notes-modal-task-title");
export const notesModalInputEl = $("#notes-modal-input");

export const notesReadModalEl = $("#notes-read-modal");
export const notesReadTaskTitleEl = $("#notes-read-task-title");
export const notesReadBodyEl = $("#notes-read-body");
export const notesReadEditBtn = $("#notes-read-edit-btn");

export const focusBtn = $("#focus-btn");
export const focusLauncherEl = $("#focus-launcher");
export const focusMinusBtn = $("#focus-minus");
export const focusPlusBtn = $("#focus-plus");
export const focusMinutesInput = $("#focus-minutes");
export const focusOverlayEl = $("#focus-overlay");
export const focusStatePrerollEl = $("#focus-state-preroll");
export const focusStateRunningEl = $("#focus-state-running");
export const focusStateDoneEl = $("#focus-state-done");
export const focusPrerollNumEl = $("#focus-preroll-num");
export const focusClockEl = $("#focus-clock");
export const focusCancelBtn = $("#focus-cancel-btn");
export const focusRestartBtn = $("#focus-restart-btn");
export const focusCloseBtn = $("#focus-close-btn");
export const focusDoneDetailEl = $("#focus-done-detail");
// Stage 5: the task bound to a running focus session (block under the now-line).
export const focusTaskEl = $("#focus-task");
export const focusTaskPriorityEl = $("#focus-task-priority");
export const focusTaskDueEl = $("#focus-task-due");
export const focusTaskNotesBtn = $("#focus-task-notes-btn");
export const focusTaskTitleEl = $("#focus-task-title");
export const focusTaskNotesEl = $("#focus-task-notes");
export const focusSnoozeBtn = $("#focus-snooze-btn");
export const focusTaskCompleteBtn = $("#focus-task-complete-btn");

// Focus queue (one task at a time).
export const queueBtn = $("#queue-btn");
export const queueOverlayEl = $("#queue-overlay");
export const queueExitBtn = $("#queue-exit-btn");
export const queueStateRunningEl = $("#queue-state-running");
export const queueStateEmptyEl = $("#queue-state-empty");
export const queueProgressEl = $("#queue-progress");
export const queuePeekEl = $("#queue-peek");
export const queuePriorityEl = $("#queue-priority");
export const queueDurationEl = $("#queue-duration");
export const queueDueEl = $("#queue-due");
export const queueTitleEl = $("#queue-title");
export const queueNotesEl = $("#queue-notes");
export const queueNotesBtn = $("#queue-notes-btn");
export const queueSkipBtn = $("#queue-skip-btn");
export const queueCompleteBtn = $("#queue-complete-btn");
export const queueEmptyCloseBtn = $("#queue-empty-close-btn");
