/** Display helpers for billing. Plans, entitlements and money are decided by the API. */
import type { components } from "@onyx/api-client";

export type Billing = components["schemas"]["BillingOut"];
export type UsageReport = components["schemas"]["UsageReportOut"];
export type StatusView = {
  label: string;
  variant: "success" | "warning" | "destructive" | "outline";
};

const STATUS: Record<string, StatusView> = {
  active: { label: "Active", variant: "success" },
  trialing: { label: "Trial", variant: "success" },
  past_due: { label: "Payment overdue", variant: "warning" },
  unpaid: { label: "Unpaid", variant: "destructive" },
  canceled: { label: "Cancelled", variant: "outline" },
  incomplete: { label: "Waiting for payment", variant: "warning" },
  incomplete_expired: { label: "Checkout expired", variant: "outline" },
};

export function billingStatus(status: string | null | undefined): StatusView {
  if (!status) return { label: "No plan", variant: "outline" };
  return STATUS[status] ?? { label: status, variant: "outline" };
}

/** Millionths of a dollar as dollars, exactly (no floating-point arithmetic on money). */
export function usd(micros: number, decimals: 2 | 6 = 2): string {
  const negative = micros < 0;
  const abs = Math.abs(Math.trunc(micros));
  const whole = Math.floor(abs / 1_000_000);
  const part = String(abs % 1_000_000).padStart(6, "0");
  const fraction = decimals === 6 ? part : part.slice(0, 2);
  return `${negative ? "-" : ""}$${whole}.${fraction}`;
}

/** The last `count` months as `YYYY-MM`, newest first. */
export function recentMonths(now: Date, count = 6): string[] {
  const months: string[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
    months.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

export const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
