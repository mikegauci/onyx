/** Display helpers for staff tasks. Who sees which task is decided by the API. */
import type { components } from "@onyx/api-client";

export type Task = components["schemas"]["TaskOut"];

/** Where a task's record lives in the dashboard, or null for kinds without a page. */
export function taskHref(
  slug: string,
  task: Pick<Task, "subject_type" | "subject_id">,
): string | null {
  const base = `/w/${encodeURIComponent(slug)}`;
  if (task.subject_type === "outbound_draft") return `${base}/m/outbound/drafts/${task.subject_id}`;
  return null;
}

/** The sidebar label, with the open count when there is one. */
export function tasksLabel(open: number): string {
  return open > 0 ? `Tasks (${open})` : "Tasks";
}
