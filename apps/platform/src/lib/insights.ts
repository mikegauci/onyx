import type { components } from "@onyx/api-client";

export type Insights = components["schemas"]["InsightsOut"];

export const RANGES = [7, 30, 90] as const;
export type Range = (typeof RANGES)[number];

export function parseRange(value: string | string[] | undefined): Range {
  const n = Number(Array.isArray(value) ? value[0] : value);
  return (RANGES as readonly number[]).includes(n) ? (n as Range) : 30;
}

/** "45 s", "4 min", "2 h 5 min", "3 d 4 h"; an em dash when there is nothing to measure. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rest = minutes % 60;
    return rest ? `${hours} h ${rest} min` : `${hours} h`;
  }
  const days = Math.floor(hours / 24);
  const rest = hours % 24;
  return rest ? `${days} d ${rest} h` : `${days} d`;
}

/** Share of `part` in `whole` as a whole percentage, or null when there is no whole. */
export function percent(part: number, whole: number): number | null {
  return whole > 0 ? Math.round((part / whole) * 100) : null;
}

/** The baseline comparison for the median first reply, e.g. "was about 2 h". */
export function baselineNote(minutes: number | null | undefined): string | null {
  return minutes === null || minutes === undefined
    ? null
    : `before Onyx: about ${formatDuration(minutes * 60)}`;
}

export const CHANNEL_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  email: "Email",
  manual: "Phone / in person",
  web: "Web chat",
};

export const RUN_REASON_LABEL: Record<string, string> = {
  model_escalated: "Asked for a person",
  low_confidence: "Not confident",
  no_lines: "Nothing to quote",
  ungrounded_sku: "Product not looked up",
  unknown_sku: "Unknown product",
  archived_sku: "Archived product",
  missing_price: "Missing price",
  missing_vat: "Missing VAT rate",
  unknown_stock: "Stock unknown",
  insufficient_stock: "Not enough stock",
  reply_mentions_amount: "Price in the reply",
  reply_ungrounded_sku: "Unchecked product in the reply",
  unknown_policy: "Unknown policy",
  unknown_source: "Unchecked document",
  no_contact: "No contact linked",
  quote_failed: "Quote refused",
  ai_unavailable: "AI unavailable",
  budget_exceeded: "AI budget used up",
  provider_failed: "AI provider failed",
};

export const SKIP_REASON_LABEL: Record<string, string> = {
  off: "Text-back off on the line",
  paused: "Paused (pilot controls)",
  not_set_up: "No template set",
  withheld: "Number withheld",
  blocked: "Caller opted out",
  recent: "Texted recently",
  fixed_line: "Landline",
};

export function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key.replaceAll("_", " ");
}
