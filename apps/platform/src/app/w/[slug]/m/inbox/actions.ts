"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import { type ConversationStatus, inboxPath } from "@/lib/inbox";

function done(slug: string, message: string): FormState {
  revalidatePath(inboxPath(slug), "layout");
  return { status: "ok", message };
}

const STATUSES: ConversationStatus[] = ["open", "waiting_on_customer", "closed"];

function statusFrom(formData: FormData, name: string): ConversationStatus | null {
  const value = text(formData, name);
  return STATUSES.includes(value as ConversationStatus) ? (value as ConversationStatus) : null;
}

// --- conversations ---------------------------------------------------------------------------

export async function createConversation(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const contactId = optionalText(formData, "contact_id");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/conversations", {
      params: { path: { slug } },
      body: {
        channel_id: text(formData, "channel_id"),
        subject: text(formData, "subject"),
        body: text(formData, "body"),
        contact_id: contactId,
        sender: contactId
          ? null
          : {
              name: optionalText(formData, "sender_name"),
              email: optionalText(formData, "sender_email"),
              phone: optionalText(formData, "sender_phone"),
            },
        // One key per form render, so a double submit records the call once.
        idempotency_key: optionalText(formData, "idempotency_key"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(inboxPath(slug), "layout");
  redirect(inboxPath(slug, "conversations", outcome.data.id));
}

export async function postMessage(
  slug: string,
  conversationId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const kind = text(formData, "kind") as "reply" | "customer" | "note";
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/conversations/{conversation_id}/messages", {
      params: { path: { slug, conversation_id: conversationId } },
      body: {
        kind,
        body: text(formData, "body"),
        set_status: statusFrom(formData, "set_status"),
        idempotency_key: optionalText(formData, "idempotency_key"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  const label = {
    reply: "Reply logged.",
    customer: "Customer message logged.",
    note: "Note added.",
  };
  return done(slug, label[kind] ?? "Saved.");
}

export async function assignConversation(
  slug: string,
  conversationId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const assignee = optionalText(formData, "assignee_user_id");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/conversations/{conversation_id}/assign", {
      params: { path: { slug, conversation_id: conversationId } },
      body: { assignee_user_id: assignee },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(
    slug,
    outcome.data.assignee
      ? `Assigned to ${outcome.data.assignee.display_name ?? "a member"}.`
      : "Unassigned.",
  );
}

export async function changeStatus(
  slug: string,
  conversationId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const status = statusFrom(formData, "status");
  if (!status) return { status: "error", message: "Choose a status." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/conversations/{conversation_id}/status", {
      params: { path: { slug, conversation_id: conversationId } },
      body: { status },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Status updated.");
}

export async function handoff(
  slug: string,
  conversationId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const handler = text(formData, "handler") === "assistant" ? "assistant" : "staff";
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/conversations/{conversation_id}/handoff", {
      params: { path: { slug, conversation_id: conversationId } },
      body: { handler, reason: optionalText(formData, "reason") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, handler === "staff" ? "Handed to staff." : "Handed to the assistant.");
}

export async function linkContact(
  slug: string,
  conversationId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/inbox/conversations/{conversation_id}", {
      params: { path: { slug, conversation_id: conversationId } },
      body: { contact_id: optionalText(formData, "contact_id") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, outcome.data.contact ? "Contact linked." : "Contact unlinked.");
}

// --- channels --------------------------------------------------------------------------------

export async function createChannel(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const kind = text(formData, "kind") as "manual" | "email" | "whatsapp" | "web";
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/channels", {
      params: { path: { slug } },
      body: {
        kind,
        name: text(formData, "name"),
        ...(kind === "email"
          ? {
              from_name: optionalText(formData, "from_name"),
              signature: optionalText(formData, "signature"),
            }
          : {}),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, `Channel ${outcome.data.name} added.`);
}

export async function setChannelDisabled(
  slug: string,
  channelId: string,
  disabled: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/inbox/channels/{channel_id}", {
      params: { path: { slug, channel_id: channelId } },
      body: { disabled },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, disabled ? "Channel disabled." : "Channel enabled.");
}

/** An email channel's sender name and signature; an empty field clears it. */
export async function updateEmailSettings(
  slug: string,
  channelId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/inbox/channels/{channel_id}", {
      params: { path: { slug, channel_id: channelId } },
      body: {
        from_name: optionalText(formData, "from_name"),
        signature: optionalText(formData, "signature"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Sender details saved.");
}

// --- suppressions ----------------------------------------------------------------------------

/** Stop emailing an address. Approved replies to it are refused until it is released. */
export async function addSuppression(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/suppressions", {
      params: { path: { slug } },
      body: { address: text(formData, "address"), note: optionalText(formData, "note") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Address blocked. Onyx will not email it.");
}

export async function releaseSuppression(
  slug: string,
  suppressionId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/inbox/suppressions/{suppression_id}/release", {
      params: { path: { slug, suppression_id: suppressionId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Address released. Onyx can email it again.");
}
