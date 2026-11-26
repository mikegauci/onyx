/** Display helpers for customer cars and reminders (VA-009). Due dates are decided by the API. */
import type { components } from "@onyx/api-client";

export type CustomerCar = components["schemas"]["CustomerCarOut"];
export type Reminder = components["schemas"]["ReminderOut"];
export type ReminderKind = components["schemas"]["ReminderKind"];
export type ReminderSettings = components["schemas"]["ReminderSettingsOut"];
export type ReminderStatus = "pending" | "sent" | "dismissed" | "skipped";

export const REMINDER_KINDS: ReminderKind[] = ["licence", "insurance", "service"];
export const REMINDER_STATUSES: ReminderStatus[] = ["pending", "skipped", "sent", "dismissed"];

export const REMINDER_KIND_LABEL: Record<ReminderKind, string> = {
  licence: "Road licence",
  insurance: "Insurance",
  service: "Service",
};

export const REMINDER_STATUS_LABEL: Record<ReminderStatus, string> = {
  pending: "To send",
  sent: "Sent",
  dismissed: "Dismissed",
  skipped: "Not sent",
};

export const REMINDER_SKIP_TEXT: Record<string, string> = {
  paused: "Reminders are paused for this car.",
  no_longer_due: "The due date changed since this reminder was created.",
  no_channel: "No WhatsApp conversation or email address to send to.",
  cannot_send: "Refused (for example, the customer opted out or the address is blocked).",
};

export function reminderSkipReason(code: string | null | undefined): string | null {
  if (!code) return null;
  return REMINDER_SKIP_TEXT[code] ?? code;
}

export const REMINDER_PARAM_LABEL: Record<string, string> = {
  first_name: "Customer’s first name",
  vehicle: "The car",
  registration: "Registration number",
  due_date: "Due date",
};

/** An ISO date (YYYY-MM-DD) as 01/03/2027; "—" when missing. */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

/** Whole days from today (UTC) to an ISO date; negative when it has passed. */
export function daysUntil(iso: string, today: Date = new Date()): number {
  const start = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const [y, m, d] = iso.split("-").map(Number);
  return Math.round((Date.UTC(y ?? 0, (m ?? 1) - 1, d ?? 1) - start) / 86_400_000);
}
