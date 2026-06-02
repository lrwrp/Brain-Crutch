// Pure HTTP wrappers. Each function returns the parsed JSON (or true/null/
// false) and never touches client-side state — callers are responsible for
// applying the result.

export async function fetchTasks() {
  const res = await fetch("/api/tasks");
  if (!res.ok) return null;
  return res.json();
}

export async function fetchInbox() {
  const res = await fetch("/api/inbox");
  if (!res.ok) return null;
  return res.json();
}

export async function createTaskRecord(body) {
  const res = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function patchTaskRecord(id, patch) {
  const res = await fetch(`/api/tasks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function deleteTaskRecord(id) {
  const res = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
  return res.ok;
}

export async function restoreTaskRecord(id) {
  const res = await fetch(`/api/tasks/${id}/restore`, { method: "POST" });
  if (!res.ok) return null;
  return res.json();
}

export async function deleteInboxItem(id) {
  const res = await fetch(`/api/inbox/${id}`, { method: "DELETE" });
  return res.ok;
}

export async function restoreInboxItem(id) {
  const res = await fetch(`/api/inbox/${id}/restore`, { method: "POST" });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchCalendarEvents(date) {
  const res = await fetch(
    `/api/calendar/events?date=${encodeURIComponent(date)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

export async function submitCapture(text) {
  const res = await fetch("/api/inbox", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.ok;
}

export async function fetchActivity() {
  const res = await fetch("/api/activity");
  if (!res.ok) return null;
  return res.json();
}

export async function pingActivity() {
  const res = await fetch("/api/activity", { method: "POST" });
  if (!res.ok) return null;
  return res.json(); // { date, count }
}
