"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { dealsPath } from "@/lib/deals";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import { hasLinkPlaceholder } from "@/lib/reviews";

export type SendState = FormState & { sent?: number };

function refresh(slug: string) {
  revalidatePath(dealsPath(slug), "layout");
}

export async function sendReviewRequests(
  slug: string,
  _prev: SendState,
  formData: FormData,
): Promise<SendState> {
  const ids = formData.getAll("request_id").map(String).filter(Boolean);
  if (ids.length === 0) return { status: "error", message: "Select at least one request." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/reviews/send", {
      params: { path: { slug } },
      body: { request_ids: ids.slice(0, 50) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  const { sent, skipped } = outcome.data;
  const parts = [`${sent.length} review request${sent.length === 1 ? "" : "s"} sent.`];
  if (skipped.length > 0) {
    parts.push(
      `${skipped.length} not sent: ${[...new Set(skipped.map((s) => s.message))].join(" ")}`,
    );
  }
  return {
    status: skipped.length > 0 && sent.length === 0 ? "error" : "ok",
    message: parts.join(" "),
    sent: sent.length,
  };
}

export async function dismissReviewRequest(
  slug: string,
  requestId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/reviews/{request_id}/dismiss", {
      params: { path: { slug, request_id: requestId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Dismissed." };
}

export async function saveReviewSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const message = optionalText(formData, "message");
  if (message !== null && !hasLinkPlaceholder(message)) {
    return {
      status: "error",
      message: "Check the highlighted fields.",
      fieldErrors: { message: "Keep {link} where the Google link goes." },
    };
  }
  const delay = Number.parseInt(text(formData, "delay_days") || "7", 10);
  const templateId = optionalText(formData, "template_id");
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/reviews/settings", {
      params: { path: { slug } },
      body: {
        google_review_url: optionalText(formData, "google_review_url"),
        delay_days: Number.isFinite(delay) ? delay : 7,
        email_subject: optionalText(formData, "email_subject"),
        message,
        template_id: templateId,
        params: templateId ? formData.getAll("param").map(String) : [],
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: outcome.data.enabled
      ? "Saved. Review requests appear after each collection."
      : "Saved. Review requests are off until you add the Google link.",
  };
}
