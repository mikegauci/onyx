"use server";

import { revalidatePath } from "next/cache";

import { type MutationOutcome, mutateApi } from "@/lib/api-client";
import { platformEnv } from "@/lib/env";

export type FormState = {
  status: "idle" | "ok" | "error";
  message?: string;
  fieldErrors?: Record<string, string>;
  requestId?: string;
  /** Set after an invitation is created: the one-time accept link to share. */
  inviteLink?: string;
};

function failure(outcome: Extract<MutationOutcome<unknown>, { ok: false }>): FormState {
  const fieldErrors: Record<string, string> = {};
  for (const detail of outcome.error?.details ?? []) {
    const field = detail.loc.at(-1);
    if (typeof field === "string" && !(field in fieldErrors)) fieldErrors[field] = detail.msg;
  }
  const message =
    outcome.status === 403
      ? "You do not have permission to do this."
      : outcome.status === 422
        ? "Check the highlighted fields."
        : outcome.status === 401
          ? "Your session has expired. Sign in again."
          : (outcome.error?.message ?? "The Onyx API is unavailable. Try again shortly.");
  return { status: "error", message, fieldErrors, requestId: outcome.requestId };
}

export async function updateWorkspace(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}", {
      params: { path: { slug } },
      body: {
        name: String(formData.get("name") ?? ""),
        timezone: String(formData.get("timezone") ?? ""),
        // Empty clears the display name and brand colour.
        display_name: String(formData.get("display_name") ?? "").trim() || null,
        brand_color: String(formData.get("brand_color") ?? "").trim() || null,
      },
    }),
  );
  if (!outcome.ok) return failure(outcome);
  revalidatePath(`/w/${slug}`, "layout");
  return { status: "ok", message: "Workspace settings saved." };
}

export async function createInvitation(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const role = String(formData.get("role") ?? "member");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/invitations", {
      params: { path: { slug } },
      body: {
        email: String(formData.get("email") ?? ""),
        role: role === "owner" || role === "admin" ? role : "member",
      },
    }),
  );
  if (!outcome.ok) return failure(outcome);
  const link = new URL("/invitations/accept", platformEnv().appUrl);
  link.searchParams.set("token", outcome.data.token);
  return {
    status: "ok",
    message: `Invitation created for ${outcome.data.email}. Email delivery arrives in PR-017; share this one-time link instead.`,
    inviteLink: link.toString(),
  };
}

function wholeNumber(formData: FormData, name: string): number | null | "invalid" {
  const raw = String(formData.get(name) ?? "").trim();
  if (raw === "") return null;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 ? value : "invalid";
}

/** Manual mode on or off (PR-018). Turning it off clears the reason. */
export async function setManualMode(
  slug: string,
  on: boolean,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const reason = String(formData.get("reason") ?? "").trim();
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/controls", {
      params: { path: { slug } },
      body: on ? { manual_mode: true, manual_mode_reason: reason || null } : { manual_mode: false },
    }),
  );
  if (!outcome.ok) return failure(outcome);
  revalidatePath(`/w/${slug}`, "layout");
  return {
    status: "ok",
    message: on
      ? "Manual mode is on. Nothing is drafted or sent automatically."
      : "Manual mode is off. The feature switches below apply again.",
  };
}

/** The feature switches and the "before Onyx" baseline (PR-018). */
export async function updateControls(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const firstReply = wholeNumber(formData, "baseline_first_reply_minutes");
  const perWeek = wholeNumber(formData, "baseline_enquiries_per_week");
  const fieldErrors: Record<string, string> = {};
  if (firstReply === "invalid") fieldErrors.baseline_first_reply_minutes = "Enter whole minutes.";
  if (perWeek === "invalid") fieldErrors.baseline_enquiries_per_week = "Enter a whole number.";
  if (firstReply === "invalid" || perWeek === "invalid") {
    return { status: "error", message: "Check the highlighted fields.", fieldErrors };
  }
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/controls", {
      params: { path: { slug } },
      body: {
        assistant_enabled: formData.get("assistant_enabled") === "on",
        text_back_enabled: formData.get("text_back_enabled") === "on",
        baseline_first_reply_minutes: firstReply,
        baseline_enquiries_per_week: perWeek,
      },
    }),
  );
  if (!outcome.ok) return failure(outcome);
  revalidatePath(`/w/${slug}`, "layout");
  return { status: "ok", message: "Pilot controls saved." };
}

/** How long conversations are kept before their text is removed (owners). */
export async function saveRetention(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const raw = String(formData.get("months") ?? "");
  const months = raw === "" ? null : Number(raw);
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/privacy/settings", {
      params: { path: { slug } },
      body: { conversation_retention_months: months },
    }),
  );
  if (!outcome.ok) return failure(outcome);
  revalidatePath(`/w/${slug}/settings/privacy`);
  return {
    status: "ok",
    message:
      months === null
        ? "Conversations are kept until you erase them."
        : `Conversations with no activity for ${months} months will have their text removed.`,
  };
}
