/** Display helpers for quotations. Every amount and rule comes from the API; no arithmetic. */
import type { components } from "@onyx/api-client";

export type QuoteSummary = components["schemas"]["QuoteSummary"];
export type QuoteDetail = components["schemas"]["QuoteDetail"];
export type QuoteStatus = components["schemas"]["QuoteStatus"];
export type QuoteLine = components["schemas"]["LineOut"];
export type QuoteWarning = components["schemas"]["WarningOut"];
export type QuotationSettings = components["schemas"]["SettingsOut"];

export function quotationsPath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/quotations`, ...parts].join("/");
}

export function euro(amount: string): string {
  return `€${amount}`;
}

export const STATUS_LABEL: Record<QuoteStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  accepted: "Accepted",
  declined: "Declined",
  cancelled: "Cancelled",
};

export const STATUS_VARIANT: Record<
  QuoteStatus,
  "default" | "secondary" | "outline" | "success" | "warning"
> = {
  draft: "secondary",
  approved: "default",
  accepted: "success",
  declined: "outline",
  cancelled: "outline",
};

export function pdfPath(slug: string, quoteId: string, version: number): string {
  return quotationsPath(slug, "quotes", quoteId, "pdf", String(version));
}
