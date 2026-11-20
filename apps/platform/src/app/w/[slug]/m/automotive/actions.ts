"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { automotivePath, type ImportPreview, SOURCE_ERROR_TEXT } from "@/lib/automotive";
import { type FormState, failureState, text } from "@/lib/form-state";

export type ImportState = FormState & { preview?: ImportPreview; applied?: boolean };

function sourceFailure(outcome: Parameters<typeof failureState>[0]): FormState {
  const state = failureState(outcome);
  const code = outcome.error?.details?.find((d) => d.type === "source")?.msg;
  return code
    ? { ...state, message: SOURCE_ERROR_TEXT[code] ?? `The site could not be read (${code}).` }
    : state;
}

/** Connect the website (and, optionally, the field map as JSON). */
export async function saveSource(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const rawMap = text(formData, "field_map");
  let fieldMap: Record<string, Record<string, unknown>> | undefined;
  if (rawMap) {
    try {
      fieldMap = JSON.parse(rawMap) as Record<string, Record<string, unknown>>;
    } catch {
      return {
        status: "error",
        message: "The field map is not valid JSON.",
        fieldErrors: { field_map: "Not valid JSON." },
      };
    }
  }
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/automotive/source", {
      params: { path: { slug } },
      body: { base_url: text(formData, "base_url"), field_map: fieldMap ?? null },
    }),
  );
  if (!outcome.ok) return sourceFailure(outcome);
  revalidatePath(automotivePath(slug), "layout");
  return {
    status: "ok",
    message: "Website saved. Preview the import to see what it would change.",
  };
}

export async function previewImport(slug: string, _prev: ImportState): Promise<ImportState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/import/preview", { params: { path: { slug } } }),
  );
  if (!outcome.ok) return sourceFailure(outcome);
  return {
    status: "ok",
    message: "Preview ready. Nothing has changed yet.",
    preview: outcome.data,
  };
}

export async function applyImport(slug: string, _prev: ImportState): Promise<ImportState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/import/apply", { params: { path: { slug } } }),
  );
  if (!outcome.ok) return sourceFailure(outcome);
  revalidatePath(automotivePath(slug), "layout");
  const d = outcome.data;
  return {
    status: "ok",
    message: `Imported: ${d.create} new, ${d.update} updated, ${d.unchanged} unchanged, ${d.withdraw} no longer listed.`,
    preview: d,
    applied: true,
  };
}
