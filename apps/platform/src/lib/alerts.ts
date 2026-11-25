/** Display helpers for stock-match alerts (VA-005). Matching and consent are decided by the API. */
import type { components } from "@onyx/api-client";

export type Wanted = components["schemas"]["WantedOut"];
export type CarMatch = components["schemas"]["MatchOut"];
export type MatchStatus = components["schemas"]["MatchStatus"];
export type AlertSettings = components["schemas"]["AlertSettingsOut"];
export type Consent = components["schemas"]["ConsentOut"];
export type ConsentMethod = components["schemas"]["ConsentMethod"];

export const MATCH_STATUS_LABEL: Record<MatchStatus, string> = {
  pending: "To send",
  sent: "Sent",
  dismissed: "Dismissed",
  skipped: "Not sent",
};

export const MATCH_STATUS_VARIANT: Record<
  MatchStatus,
  "success" | "warning" | "outline" | "secondary"
> = {
  pending: "warning",
  sent: "success",
  dismissed: "outline",
  skipped: "secondary",
};

/** Why a match was not sent, for staff. Codes come from the API. */
export const SKIP_REASON_TEXT: Record<string, string> = {
  car_not_available: "The car is no longer available.",
  no_longer_matches: "The buyer’s criteria no longer match this car.",
  no_consent: "The customer has not agreed to car alerts.",
  no_phone: "The customer has no phone number.",
  no_whatsapp_conversation: "The customer has never written on the alerts WhatsApp number.",
  cannot_send: "WhatsApp refused it (for example, the customer opted out).",
};

export function skipReason(code: string | null | undefined): string | null {
  if (!code) return null;
  return SKIP_REASON_TEXT[code] ?? code;
}

export const CONSENT_METHOD_LABEL: Record<ConsentMethod, string> = {
  in_person: "In person",
  phone: "On the phone",
  whatsapp: "On WhatsApp",
  email: "By email",
  form: "On a form",
};

export const PARAM_LABEL: Record<string, string> = {
  first_name: "Customer’s first name",
  vehicle: "Car title",
  price: "Car price",
  link: "Link to the listing",
};

/** A one-line summary of what a buyer wants: "Volkswagen Golf · up to €18,000 · from 2018". */
export function wantedSummary(
  w: Pick<Wanted, "make" | "model" | "price_max_cents" | "year_min" | "mileage_max_km" | "fuel">,
): string {
  const euros = (cents: number) => `€${Math.floor(cents / 100).toLocaleString("en-GB")}`;
  return [
    [w.make, w.model].filter(Boolean).join(" ") || null,
    w.price_max_cents !== null ? `up to ${euros(w.price_max_cents)}` : null,
    w.year_min !== null ? `from ${w.year_min}` : null,
    w.mileage_max_km !== null ? `under ${w.mileage_max_km.toLocaleString("en-GB")} km` : null,
    w.fuel,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Euros typed by staff ("18,000" or "18000.50") as cents; null when blank or invalid. */
export function centsFromEuros(raw: string): number | null {
  const cleaned = raw.replace(/[€,\s]/g, "");
  if (cleaned === "" || !/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole = "0", part = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(part.padEnd(2, "0"));
}
