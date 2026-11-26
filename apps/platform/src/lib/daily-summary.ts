/** Display helpers for the daily owner summary (VA-010). Figures and text come from the API. */
import type { components } from "@onyx/api-client";

export type SummarySettings = components["schemas"]["SummarySettingsOut"];
export type SummaryPreview = components["schemas"]["SummaryPreviewOut"];
export type SummaryHistoryItem = components["schemas"]["SummaryHistoryItem"];
export type SummaryResult = components["schemas"]["SummarySendResultOut"];
export type SummaryStatus = "sending" | "sent" | "partly_sent" | "failed";

export const MAX_RECIPIENTS = 5;
export const PARAM_KEYS = ["workspace", "date", "summary"] as const;
export type SummaryParam = (typeof PARAM_KEYS)[number];

export const PARAM_LABEL: Record<SummaryParam, string> = {
  workspace: "Workspace name",
  date: "Date (dd/mm/yyyy)",
  summary: "The summary on one line",
};

export const STATUS_LABEL: Record<SummaryStatus, string> = {
  sending: "Not confirmed",
  sent: "Sent",
  partly_sent: "Partly sent",
  failed: "Not sent",
};

export const REASON_TEXT: Record<string, string> = {
  no_template: "WhatsApp needs an approved utility template.",
  not_a_member: "This person is no longer a member of the workspace.",
  email_not_configured: "Email is not set up on this platform.",
  whatsapp_not_configured: "WhatsApp is not set up on this platform.",
  whatsapp_not_connected: "The template’s WhatsApp number is not connected.",
};

export function reasonText(code: string | null | undefined): string | null {
  if (!code) return null;
  if (REASON_TEXT[code]) return REASON_TEXT[code];
  if (code.startsWith("email_")) return "The email provider refused it.";
  if (code.startsWith("whatsapp_")) return "WhatsApp refused it.";
  return code;
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status as SummaryStatus] ?? status;
}

/** "19:00:00" or "19:00" from the API → "19:00" for a time input. */
export function timeValue(value: string): string {
  return value.slice(0, 5);
}

/** A phone number as typed → E.164, or null if it is not one. Spaces and dashes are ignored. */
export function e164(value: string): string | null {
  const compact = value.replace(/[\s-]/g, "");
  if (compact === "") return null;
  const withPlus = compact.startsWith("00") ? `+${compact.slice(2)}` : compact;
  return /^\+[1-9]\d{6,14}$/.test(withPlus) ? withPlus : null;
}
