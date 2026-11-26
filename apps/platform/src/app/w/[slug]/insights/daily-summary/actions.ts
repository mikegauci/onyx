"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import {
  e164,
  MAX_RECIPIENTS,
  PARAM_KEYS,
  reasonText,
  type SummaryParam,
} from "@/lib/daily-summary";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

function refresh(slug: string) {
  revalidatePath(`/w/${slug}/insights/daily-summary`);
}

export async function saveSummarySettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const ids = formData.getAll("recipient").map(String).filter(Boolean);
  if (ids.length > MAX_RECIPIENTS) {
    return { status: "error", message: `Choose up to ${MAX_RECIPIENTS} people.` };
  }
  const fieldErrors: Record<string, string> = {};
  const recipients = ids.map((id) => {
    const typed = text(formData, `whatsapp_${id}`);
    const whatsapp = e164(typed);
    if (typed && !whatsapp) {
      fieldErrors[`whatsapp_${id}`] =
        "Enter the number with its country code, e.g. +356 7900 0001.";
    }
    return { user_id: id, email: formData.get(`email_${id}`) === "on", whatsapp };
  });
  if (Object.keys(fieldErrors).length > 0) {
    return { status: "error", message: "Check the highlighted fields.", fieldErrors };
  }
  const templateId = optionalText(formData, "template_id");
  const params = templateId
    ? formData
        .getAll("param")
        .map(String)
        .filter((p): p is SummaryParam => (PARAM_KEYS as readonly string[]).includes(p))
    : [];
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/insights/daily-summary/settings", {
      params: { path: { slug } },
      body: {
        enabled: formData.get("enabled") === "on",
        send_at: text(formData, "send_at") || "19:00",
        recipients,
        template_id: templateId,
        params,
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Saved." };
}

export async function sendTestSummary(slug: string): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/insights/daily-summary/test", { params: { path: { slug } } }),
  );
  if (!outcome.ok) return failureState(outcome);
  const results = outcome.data.results;
  const sent = results.filter((r) => r.status === "sent").map((r) => r.channel);
  const problems = results
    .filter((r) => r.status !== "sent")
    .map((r) => `${r.channel === "email" ? "Email" : "WhatsApp"}: ${reasonText(r.reason)}`);
  return {
    status: sent.length > 0 ? "ok" : "error",
    message: [
      sent.length > 0 ? `Test sent by ${sent.join(" and ")}.` : "The test was not sent.",
      ...problems,
    ].join(" "),
  };
}
