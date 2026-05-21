// DOM element handles, looked up once at module load. All other modules
// import these instead of repeating `document.querySelector` calls.

const $ = (sel) => document.querySelector(sel);

export const clockEl = $("#clock");
export const dateEl = $("#date");
export const winsEl = $("#wins");
export const winsStarsEl = $("#wins-stars");

export const list = $("#inbox-list");
export const countEl = $("#inbox-count");
export const emptyEl = $("#inbox-empty");

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

export const taskForm = $("#task-form");
export const taskInputEl = $("#task-input");
export const tasksCountEl = $("#tasks-count");
export const tasksListEl = $("#tasks-list");
export const tasksEmptyEl = $("#tasks-empty");
export const tasksSnoozedDetailsEl = $("#tasks-snoozed-details");
export const tasksSnoozedSummaryEl = $("#tasks-snoozed-summary");
export const tasksSnoozedListEl = $("#tasks-snoozed-list");

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
