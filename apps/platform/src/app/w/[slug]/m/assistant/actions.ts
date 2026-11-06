"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { type AssistantRun, assistantPath, RUN_TIMEOUT_MS, TOPIC_PATTERN } from "@/lib/assistant";
import { type FormState, failureState, text } from "@/lib/form-state";
import { inboxPath } from "@/lib/inbox";

export type RunState = FormState & { run?: AssistantRun };

/** Ask the assistant to draft a reply and quote. The API decides everything; nothing is sent. */
export async function runAssistant(
  slug: string,
  conversationId: string,
  _prev: RunState,
): Promise<RunState> {
  void _prev;
  const outcome = await mutateApi(
    (api) =>
      api.POST("/v1/w/{slug}/assistant/conversations/{conversation_id}/runs", {
        params: { path: { slug, conversation_id: conversationId } },
      }),
    fetch,
    RUN_TIMEOUT_MS,
  );
  if (!outcome.ok) {
    // No error body: the request timed out or the API is down. The run may still finish.
    if (outcome.status === 503 && !outcome.error) {
      return {
        status: "error",
        message:
          "The assistant did not answer in time. Refresh the page in a minute: if it finished, its note is in the messages.",
        requestId: outcome.requestId,
      };
    }
    return failureState(outcome);
  }
  revalidatePath(inboxPath(slug), "layout");
  const run = outcome.data;
  return {
    status: "ok",
    message:
      run.outcome === "drafted"
        ? `Draft quote ${run.quote?.number ?? ""} created. The draft reply is in the messages as a note.`
        : "The assistant handed this to staff. Its note in the messages explains why.",
    run,
  };
}

export async function savePolicy(
  slug: string,
  existingTopic: string | null,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const topic = existingTopic ?? text(formData, "topic").toLowerCase();
  if (!TOPIC_PATTERN.test(topic)) {
    return {
      status: "error",
      message: "Check the highlighted fields.",
      fieldErrors: {
        topic: "Use 2–40 lower-case letters, digits or underscores, starting with a letter.",
      },
    };
  }
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/assistant/policies/{topic}", {
      params: { path: { slug, topic } },
      body: { title: text(formData, "title"), body: text(formData, "body") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(assistantPath(slug));
  return { status: "ok", message: `Policy “${outcome.data.title}” saved.` };
}

export async function deletePolicy(
  slug: string,
  topic: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.DELETE("/v1/w/{slug}/assistant/policies/{topic}", {
      params: { path: { slug, topic } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(assistantPath(slug));
  return { status: "ok", message: "Policy deleted." };
}
