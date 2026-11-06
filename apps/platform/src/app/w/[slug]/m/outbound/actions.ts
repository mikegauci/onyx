"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import { inboxPath } from "@/lib/inbox";
import { isEdited, outboundPath } from "@/lib/outbound";

function refresh(slug: string) {
  revalidatePath(outboundPath(slug), "layout");
  revalidatePath(inboxPath(slug), "layout");
}

/** A staff-written reply, waiting for approval. Nothing is sent. */
export async function createDraft(
  slug: string,
  conversationId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/outbound/conversations/{conversation_id}/drafts", {
      params: { path: { slug, conversation_id: conversationId } },
      body: { body: text(formData, "body"), quote_id: optionalText(formData, "quote_id") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Reply saved. It waits for an admin or owner to approve it." };
}

/** Save an edit as a new revision. An approved reply goes back to waiting for approval. */
export async function reviseDraft(
  slug: string,
  draftId: string,
  baseRevision: number,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/outbound/drafts/{draft_id}/revisions", {
      params: { path: { slug, draft_id: draftId } },
      body: { body: text(formData, "body"), base_revision: baseRevision },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message:
      outcome.data.current_revision > baseRevision
        ? `Saved as revision ${outcome.data.current_revision}. It needs approval before sending.`
        : "No changes to save.",
  };
}

/** Approve the revision on screen; with edited text, approve that edit instead. */
export async function approveDraft(
  slug: string,
  draftId: string,
  revision: number,
  original: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const edited = text(formData, "body");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/outbound/drafts/{draft_id}/approve", {
      params: { path: { slug, draft_id: draftId } },
      body: { revision, ...(edited && isEdited(original, edited) ? { body: edited } : {}) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: `Revision ${outcome.data.approved_revision ?? revision} approved. It can be sent now.`,
  };
}

export async function rejectDraft(
  slug: string,
  draftId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/outbound/drafts/{draft_id}/reject", {
      params: { path: { slug, draft_id: draftId } },
      body: { reason: text(formData, "reason") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Reply rejected. Nothing was sent." };
}

/** Send the approved revision. The API sends it once, however often this is submitted. */
export async function sendDraft(
  slug: string,
  draftId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/outbound/drafts/{draft_id}/send", {
      params: { path: { slug, draft_id: draftId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Reply sent. It is now in the conversation." };
}

export async function updateExpiry(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const hours = Number(text(formData, "expiry_hours"));
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/outbound/settings", {
      params: { path: { slug } },
      body: { expiry_hours: Number.isInteger(hours) ? hours : 0 },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: `Drafts now stay valid for ${outcome.data.expiry_hours} hours.` };
}
