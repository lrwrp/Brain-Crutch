// Tiny pub-sub bus. Used so mutations in state.js can announce "a task
// changed" without knowing which renderers care, and so future features
// (wins counter, active-task highlight) can subscribe to just the slice of
// activity they need.
//
// Handlers run synchronously in registration order. Throwing handlers are
// logged but don't stop later subscribers — keeping one buggy listener from
// taking down the whole UI on any mutation.

class Emitter {
  constructor() {
    this.handlers = new Map();
  }

  on(event, fn) {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set());
    this.handlers.get(event).add(fn);
    return () => this.off(event, fn);
  }

  off(event, fn) {
    this.handlers.get(event)?.delete(fn);
  }

  emit(event, payload) {
    const set = this.handlers.get(event);
    if (!set) return;
    for (const fn of set) {
      try {
        fn(payload);
      } catch (err) {
        console.error(`event handler for ${event} threw`, err);
      }
    }
  }
}

export const bus = new Emitter();

// Event vocabulary. Importers reference these constants so a typo surfaces
// at module-load time instead of as a silent dead subscription.
export const EVENTS = Object.freeze({
  TASK_CREATED: "task.created",
  TASK_CHANGED: "task.changed",
  TASK_DELETED: "task.deleted",
  TASK_COMPLETED: "task.completed",
  INBOX_CREATED: "inbox.created",
  INBOX_DELETED: "inbox.deleted",
  DAY_CHANGED: "day.changed",
});
