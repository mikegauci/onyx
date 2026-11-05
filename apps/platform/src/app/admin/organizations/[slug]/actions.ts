"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";

export type ToggleState = { status: "idle" | "ok" | "error"; message?: string; requestId?: string };

export async function setModule(slug: string, key: string, enabled: boolean): Promise<ToggleState> {
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/admin/organizations/{slug}/modules/{key}", {
      params: { path: { slug, key } },
      body: { enabled },
    }),
  );
  if (!outcome.ok) {
    return {
      status: "error",
      message: outcome.error?.message ?? "The Onyx API is unavailable. Try again shortly.",
      requestId: outcome.requestId,
    };
  }
  revalidatePath(`/admin/organizations/${slug}`);
  return { status: "ok", message: `${key} ${enabled ? "enabled" : "disabled"}.` };
}
