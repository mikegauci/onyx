"use server";

import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";

export type AcceptState = { error?: string; requestId?: string };

const MESSAGES: Record<number, string> = {
  404: "This invitation was not found, or it was sent to a different email address.",
  409: "You are already a member of this workspace.",
  410: "This invitation has expired or was already used. Ask an admin for a new one.",
};

export async function acceptInvitation(
  _prev: AcceptState,
  formData: FormData,
): Promise<AcceptState> {
  const token = String(formData.get("token") ?? "");
  const outcome = await mutateApi((api) => api.POST("/v1/invitations/accept", { body: { token } }));
  if (outcome.ok) redirect(`/w/${outcome.data.slug}`);
  if (outcome.status === 401) {
    redirect(`/login?next=${encodeURIComponent(`/invitations/accept?token=${token}`)}`);
  }
  return {
    error: MESSAGES[outcome.status] ?? "The Onyx API is unavailable. Try again shortly.",
    requestId: outcome.requestId,
  };
}
