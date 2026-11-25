"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { crmPath } from "@/lib/crm";
import { type FormState, failureState, text } from "@/lib/form-state";

export async function eraseContact(
  slug: string,
  contactId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/privacy/contacts/{contact_id}/erase", {
      params: { path: { slug, contact_id: contactId } },
      body: { confirm_name: text(formData, "confirm_name") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(crmPath(slug), "layout");
  return {
    status: "ok",
    message: `Erased. ${outcome.data.files_deleted} document file${outcome.data.files_deleted === 1 ? "" : "s"} deleted.`,
  };
}
