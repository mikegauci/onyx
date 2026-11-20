/** Display helpers for tenant onboarding and settings. The API validates and decides. */
import type { components } from "@onyx/api-client";

export type InvitationState = components["schemas"]["InvitationState"];
export type AdminInvitation = components["schemas"]["AdminInvitationOut"];
export type IntegrationStatus = components["schemas"]["IntegrationStatus"];

export const SLUG_PATTERN = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

/** A URL slug suggested from an organisation name: "Ventur Auto Import" → "ventur-auto-import". */
export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/ħ/g, "h")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+/, "")
    .slice(0, 63)
    .replace(/-+$/, "");
}

const HEX = /^#[0-9a-f]{6}$/i;

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG contrast of a #rrggbb colour against white text, or null for an invalid colour. */
export function contrastWithWhite(color: string): number | null {
  if (!HEX.test(color)) return null;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16)) as [
    number,
    number,
    number,
  ];
  const luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  return 1.05 / (luminance + 0.05);
}

/** The API refuses brand colours below WCAG AA (4.5:1) against white text. */
export const MIN_BRAND_CONTRAST = 4.5;

export const INVITATION_STATE_LABEL: Record<InvitationState, string> = {
  pending: "Waiting to be accepted",
  accepted: "Accepted",
  revoked: "Revoked",
  expired: "Expired",
};

export const INVITATION_STATE_VARIANT: Record<
  InvitationState,
  "warning" | "success" | "outline" | "destructive"
> = {
  pending: "warning",
  accepted: "success",
  revoked: "outline",
  expired: "outline",
};

/** AI budgets are stored in millionths of a US dollar. */
export function usdFromMicros(micros: number | null | undefined): string {
  if (micros === null || micros === undefined) return "No limit set";
  return `$${(micros / 1_000_000).toFixed(2)}`;
}

/** The accept link for an invitation token (shown once, never stored by the dashboard). */
export function inviteLink(appUrl: string, token: string): string {
  const link = new URL("/invitations/accept", appUrl);
  link.searchParams.set("token", token);
  return link.toString();
}
