"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import {
  duplicateOf,
  fileProblem,
  knowledgePath,
  type SearchOut,
  uploadFailureMessage,
} from "@/lib/knowledge";

/** A form state that may point at the document an upload duplicates. */
export type UploadState = FormState & { existingId?: string };

// Indexing embeds every passage inside the request, so allow far longer than a normal call.
const UPLOAD_TIMEOUT_MS = 90_000;

type FileInput = { filename: string; content_base64: string };

async function fileFrom(formData: FormData): Promise<FileInput | UploadState> {
  const file = formData.get("file");
  const problem = file instanceof File ? fileProblem(file.name, file.size) : "Choose a file.";
  if (problem || !(file instanceof File)) {
    return {
      status: "error",
      message: problem ?? "Choose a file.",
      fieldErrors: { file: problem ?? "Required." },
    };
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  return { filename: file.name.slice(0, 255), content_base64: bytes.toString("base64") };
}

function uploadFailure(outcome: Parameters<typeof failureState>[0]): UploadState {
  const existingId = duplicateOf(outcome);
  if (existingId) {
    return {
      status: "error",
      message: "This file is already in the workspace.",
      fieldErrors: { file: "Already uploaded." },
      existingId,
      requestId: outcome.requestId,
    };
  }
  const state = failureState(outcome);
  const message = uploadFailureMessage(outcome.status);
  // The API's field errors name `content_base64`; the form calls that field `file`.
  const fileError = state.fieldErrors?.content_base64 ?? state.fieldErrors?.filename;
  return {
    ...state,
    message: message ?? state.message,
    fieldErrors: fileError ? { ...state.fieldErrors, file: fileError } : state.fieldErrors,
  };
}

export async function uploadDocument(
  slug: string,
  _prev: UploadState,
  formData: FormData,
): Promise<UploadState> {
  const file = await fileFrom(formData);
  if ("status" in file) return file;
  const outcome = await mutateApi(
    (api) =>
      api.POST("/v1/w/{slug}/knowledge/documents", {
        params: { path: { slug } },
        body: { title: text(formData, "title"), ...file },
      }),
    fetch,
    UPLOAD_TIMEOUT_MS,
  );
  if (!outcome.ok) return uploadFailure(outcome);
  revalidatePath(knowledgePath(slug), "layout");
  redirect(knowledgePath(slug, "documents", outcome.data.id));
}

export async function replaceDocument(
  slug: string,
  documentId: string,
  _prev: UploadState,
  formData: FormData,
): Promise<UploadState> {
  const file = await fileFrom(formData);
  if ("status" in file) return file;
  const outcome = await mutateApi(
    (api) =>
      api.PUT("/v1/w/{slug}/knowledge/documents/{document_id}/file", {
        params: { path: { slug, document_id: documentId } },
        body: { title: optionalText(formData, "title"), ...file },
      }),
    fetch,
    UPLOAD_TIMEOUT_MS,
  );
  if (!outcome.ok) return uploadFailure(outcome);
  revalidatePath(knowledgePath(slug), "layout");
  return { status: "ok", message: `File replaced. This is now version ${outcome.data.version}.` };
}

export async function deleteDocument(
  slug: string,
  documentId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.DELETE("/v1/w/{slug}/knowledge/documents/{document_id}", {
      params: { path: { slug, document_id: documentId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(knowledgePath(slug), "layout");
  redirect(knowledgePath(slug));
}

/** A search's outcome for the form: the API's hits, or why there are none. */
export type SearchState = FormState & { query?: string; result?: SearchOut };

// Search embeds the question, so give it a little longer than a plain read.
const SEARCH_TIMEOUT_MS = 20_000;

export async function searchKnowledge(
  slug: string,
  _prev: SearchState,
  formData: FormData,
): Promise<SearchState> {
  const query = text(formData, "query");
  const outcome = await mutateApi(
    (api) =>
      api.POST("/v1/w/{slug}/knowledge/search", {
        params: { path: { slug } },
        body: { query, limit: 8 },
      }),
    fetch,
    SEARCH_TIMEOUT_MS,
  );
  if (!outcome.ok) return { ...failureState(outcome), query };
  return { status: "idle", query, result: outcome.data };
}
