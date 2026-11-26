/** Display helpers for Google review requests (VA-009). What is due and sendable is decided by the API. */
import type { components } from "@onyx/api-client";

export type ReviewRequest = components["schemas"]["ReviewRequestOut"];
export type ReviewStatus = components["schemas"]["ReviewStatus"];
export type ReviewSettings = components["schemas"]["ReviewSettingsOut"];

export const REVIEW_STATUSES: ReviewStatus[] = ["pending", "skipped", "sent", "dismissed"];

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: "To send",
  sent: "Sent",
  dismissed: "Dismissed",
  skipped: "Not sent",
};

export const REVIEW_STATUS_VARIANT: Record<
  ReviewStatus,
  "success" | "warning" | "outline" | "secondary"
> = {
  pending: "warning",
  sent: "success",
  dismissed: "outline",
  skipped: "secondary",
};

/** Why a request was not sent, for staff. Codes come from the API. */
export const REVIEW_SKIP_TEXT: Record<string, string> = {
  no_channel: "No WhatsApp conversation or email address to send to.",
  cannot_send: "Refused (for example, the customer opted out or the address is blocked).",
  not_set_up: "Add the Google review link first.",
  erased: "The customer’s data was erased.",
};

export function reviewSkipReason(code: string | null | undefined): string | null {
  if (!code) return null;
  return REVIEW_SKIP_TEXT[code] ?? code;
}

export const REVIEW_PARAM_LABEL: Record<string, string> = {
  first_name: "Customer’s first name",
  vehicle: "The car (deal title)",
  link: "Google review link",
};

/** Whether the message keeps the {link} placeholder the API requires. */
export function hasLinkPlaceholder(message: string): boolean {
  return message.includes("{link}");
}
