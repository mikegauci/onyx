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
