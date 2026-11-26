/** Display helpers for in-house finance schedules (VA-008). Allocation and states come from the API. */
import type { components } from "@onyx/api-client";

export type Schedule = components["schemas"]["ScheduleDetail"];
export type ScheduleSummary = components["schemas"]["ScheduleSummary"];
export type ScheduleStatus = components["schemas"]["ScheduleStatus"];
export type InstallmentState = components["schemas"]["InstallmentState"];
export type PaymentMethod = components["schemas"]["PaymentMethod"];

export const SCHEDULE_STATUS_LABEL: Record<ScheduleStatus, string> = {
  active: "Active",
  completed: "Paid in full",
  cancelled: "Cancelled",
};

export const INSTALLMENT_LABEL: Record<InstallmentState, string> = {
  paid: "Paid",
  part_paid: "Part paid",
  overdue: "Overdue",
  due_today: "Due today",
  upcoming: "Upcoming",
};

export const INSTALLMENT_VARIANT: Record<
  InstallmentState,
  "success" | "warning" | "destructive" | "outline" | "secondary"
> = {
  paid: "success",
  part_paid: "secondary",
  overdue: "destructive",
  due_today: "warning",
  upcoming: "outline",
};

export const METHOD_LABEL: Record<PaymentMethod, string> = {
  cash: "Cash",
  bank_transfer: "Bank transfer",
  card: "Card",
  cheque: "Cheque",
  other: "Other",
};

/** Share of the total paid, 0–100, for a progress bar. */
export function paidPercent(s: Pick<ScheduleSummary, "paid_cents" | "total_cents">): number {
  if (s.total_cents <= 0) return 0;
  return Math.min(100, Math.round((s.paid_cents / s.total_cents) * 100));
}

export type PaymentReminder = components["schemas"]["PaymentReminderOut"];
export type PaymentReminderSettings = components["schemas"]["PaymentReminderSettingsOut"];
export type PaymentReminderKind = PaymentReminder["kind"];

export const PAYMENT_REMINDER_KINDS: PaymentReminderKind[] = ["before_due", "overdue"];

export const PAYMENT_REMINDER_LABEL: Record<PaymentReminderKind, string> = {
  before_due: "Due soon",
  overdue: "Overdue",
};

export const PAYMENT_PARAM_LABEL: Record<string, string> = {
  first_name: "Customer’s first name",
  vehicle: "The car",
  amount: "Amount owed",
  due_date: "Due date",
};

export const PAYMENT_SKIP_TEXT: Record<string, string> = {
  paid: "The installment has been paid since.",
  paused: "Reminders are paused, or the schedule is no longer active.",
  no_channel: "No WhatsApp conversation or email address to send to.",
  cannot_send: "Refused (for example, the customer opted out or the address is blocked).",
  erased: "The customer’s data was erased.",
};

export function paymentSkipReason(code: string | null | undefined): string | null {
  if (!code) return null;
  return PAYMENT_SKIP_TEXT[code] ?? code;
}
