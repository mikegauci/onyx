/** Display helpers for outbound replies. Approval, expiry and sending rules live in the API. */
import type { components } from "@onyx/api-client";

export type Draft = components["schemas"]["DraftOut"];
export type DraftDetail = components["schemas"]["DraftDetail"];
export type DraftStatus = components["schemas"]["DraftStatus"];
export type Revision = components["schemas"]["RevisionOut"];

export function outboundPath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/outbound`, ...parts].join("/");
}

export const DRAFT_STATUS_LABEL: Record<DraftStatus, string> = {
  pending: "Waiting for approval",
  approved: "Approved, not sent",
  sent: "Sent",
  rejected: "Rejected",
  expired: "Expired",
  superseded: "Replaced by a newer draft",
};

export const DRAFT_STATUS_VARIANT: Record<
  DraftStatus,
  "warning" | "info" | "success" | "destructive" | "outline"
> = {
  pending: "warning",
  approved: "info",
  sent: "success",
  rejected: "destructive",
  expired: "outline",
  superseded: "outline",
};

export function originLabel(draft: Pick<Draft, "origin">): string {
  return draft.origin === "assistant" ? "Drafted by the assistant" : "Drafted by staff";
}

export function revisionAuthor(revision: Revision): string {
  if (revision.author_kind === "assistant") return "Assistant";
  return revision.author?.label ?? "Former member";
}

export type DraftControls = {
  canEdit: boolean;
  canApprove: boolean;
  canReject: boolean;
  canSend: boolean;
  /** Approve the text on screen and send it in one step (approvers who may also send). */
  canApproveAndSend: boolean;
  /** Why the reply cannot be sent yet, for the person looking at it; null when it can. */
  sendHint: string | null;
  /** Why approval is blocked (from the API), or null. */
  approveHint: string | null;
};

/**
 * Which buttons to show. A convenience only: the API checks the permission, the state, the
 * revision on screen, expiry and the quote on every request.
 */
export function draftControls(draft: Draft, permissions: readonly string[]): DraftControls {
  const open = draft.status === "pending" || draft.status === "approved";
  const write = permissions.includes("outbound.write");
  const approve = permissions.includes("outbound.approve");
  const quoteBlock = draft.quote?.blocked?.message ?? null;
  let sendHint: string | null = null;
  if (draft.status === "pending") {
    sendHint = approve
      ? (quoteBlock ?? "Approve the reply before sending it.")
      : "An admin or owner must approve this reply before it can be sent.";
  }
  return {
    canEdit: open && write,
    canApprove: open && approve && quoteBlock === null,
    canReject: open && approve,
    canSend: draft.status === "approved" && write,
    canApproveAndSend: open && approve && write && quoteBlock === null,
    sendHint,
    approveHint: open && approve ? quoteBlock : null,
  };
}

/** Draft text and the approver's edit compared as the API compares them (trimmed). */
export function isEdited(original: string, edited: string): boolean {
  return original.trim() !== edited.trim();
}
