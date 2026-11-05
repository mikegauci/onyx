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
