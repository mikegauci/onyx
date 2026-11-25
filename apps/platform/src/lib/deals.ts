/** Display helpers for deals (VA-007). Stages, rules and documents are decided by the API. */
import type { components } from "@onyx/api-client";

export type Deal = components["schemas"]["DealDetail"];
export type DealSummary = components["schemas"]["DealSummary"];
export type DealStage = components["schemas"]["DealStage"];
export type DealDocument = components["schemas"]["DealDocumentOut"];
export type DocumentState = components["schemas"]["DealDocumentState"];
export type DepositMethod = components["schemas"]["DealDepositMethod"];
export type DealSettings = components["schemas"]["DealSettingsOut"];

export function dealsPath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/deals`, ...parts].join("/");
}

/** The board's columns, in order. Collected and cancelled deals are listed separately. */
export const BOARD_STAGES: DealStage[] = [
  "reserved",
  "deposit_received",
  "documents",
  "finance",
  "sold",
];

export const STAGE_LABEL: Record<DealStage, string> = {
  reserved: "Reserved",
  deposit_received: "Deposit received",
  documents: "Documents",
  finance: "Finance",
  sold: "Sold",
  collected: "Collected",
  cancelled: "Cancelled",
};

export const STAGE_VARIANT: Record<
  DealStage,
  "default" | "info" | "warning" | "success" | "secondary" | "outline"
> = {
  reserved: "warning",
  deposit_received: "info",
  documents: "info",
  finance: "info",
  sold: "success",
  collected: "secondary",
  cancelled: "outline",
};

export const DOCUMENT_STATE_LABEL: Record<DocumentState, string> = {
  missing: "Missing",
  received: "Received, to check",
  verified: "Verified",
  rejected: "Rejected",
};

export const DOCUMENT_STATE_VARIANT: Record<
  DocumentState,
  "outline" | "warning" | "success" | "destructive"
> = {
  missing: "outline",
  received: "warning",
  verified: "success",
  rejected: "destructive",
};

export const DEPOSIT_METHOD_LABEL: Record<DepositMethod, string> = {
  cash: "Cash",
  card: "Card",
  bank_transfer: "Bank transfer",
  other: "Other",
};

/** The stages a deal can be moved to from `stage`, for the stage picker. The API re-checks. */
export function nextStages(deal: Pick<Deal, "stage" | "financed">): DealStage[] {
  if (deal.stage === "collected" || deal.stage === "cancelled") return [];
  if (deal.stage === "sold") return ["collected"];
  const open: DealStage[] = ["reserved", "deposit_received", "documents"];
  if (deal.financed) open.push("finance");
  return [...open.filter((s) => s !== deal.stage), "sold", "cancelled"];
}

const EVENT_LABEL: Record<string, string> = {
  created: "Deal created",
  updated: "Details changed",
  deposit_recorded: "Deposit recorded",
  document_added: "Document added to the checklist",
  document_received: "Document received",
  document_verified: "Document verified",
  document_rejected: "Document rejected",
};

export function eventLabel(event: components["schemas"]["DealEventOut"]): string {
  if (event.kind === "stage_changed" && event.to_stage) {
    const stage = STAGE_LABEL[event.to_stage as DealStage] ?? event.to_stage;
    return event.details.override
      ? `Marked ${stage.toLowerCase()} (owner override)`
      : `Moved to ${stage.toLowerCase()}`;
  }
  const base = EVENT_LABEL[event.kind] ?? event.kind.replaceAll("_", " ");
  const document = typeof event.details.document === "string" ? `: ${event.details.document}` : "";
  return `${base}${document}`;
}

/** Whole euros or cents from a form field ("16,500" or "16500.50") to integer cents. */
export function centsFrom(value: string): number | null | "invalid" {
  const clean = value.replace(/[€,\s]/g, "");
  if (clean === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return "invalid";
  const [whole, part = ""] = clean.split(".");
  return Number(whole) * 100 + Number(part.padEnd(2, "0"));
}
