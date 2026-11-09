/** Display helpers for knowledge documents. Extraction, limits and search live in the API. */
import type { components } from "@onyx/api-client";

import type { MutationOutcome } from "./api-client";

export type KnowledgeDocument = components["schemas"]["DocumentOut"];
export type KnowledgeDocumentDetail = components["schemas"]["DocumentDetail"];
export type DocumentFormat = components["schemas"]["DocumentFormat"];
export type SearchOut = components["schemas"]["SearchOut"];
export type SearchHit = components["schemas"]["SearchHit"];
export type RunSource = components["schemas"]["CitedSourceOut"];

export function knowledgePath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/knowledge`, ...parts].join("/");
}

export const FORMAT_LABEL: Record<DocumentFormat, string> = {
  pdf: "PDF",
  text: "Text",
  markdown: "Markdown",
};

/** The file types the API reads, by extension (the API decides the format the same way). */
export const ACCEPT = ".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown";
const EXTENSIONS = [".pdf", ".txt", ".md", ".markdown"];

/**
 * The largest file the screens send. The API takes 5 MB, but Vercel refuses request bodies over
 * 4.5 MB before the server action runs, so the browser-to-app hop is the tighter limit.
 */
export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

/** Why a chosen file cannot be uploaded, or null when it may be sent to the API. */
export function fileProblem(name: string, size: number): string | null {
  if (size === 0) return "Choose a file.";
  const lower = name.toLowerCase();
  if (!EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return "Upload a PDF, a .txt or a .md file. Word files are not supported yet.";
  }
  if (size > MAX_UPLOAD_BYTES) return "The file is larger than 4 MB.";
  return null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "Page 3" for PDF passages; null when the format has no pages. */
export function pageLabel(page: number | null | undefined): string | null {
  return page == null ? null : `Page ${page}`;
}

/** The existing document's id when an upload was refused as a duplicate (409). */
export function duplicateOf(outcome: Extract<MutationOutcome<unknown>, { ok: false }>) {
  if (outcome.status !== 409) return null;
  const detail = outcome.error?.details?.find((d) => d.type === "duplicate");
  return detail?.ref ?? null;
}

/** What a failed upload means for the person, for the statuses the API documents. */
export function uploadFailureMessage(status: number): string | null {
  if (status === 503) {
    return "Documents cannot be indexed right now because AI is unavailable. Try again later.";
  }
  if (status === 429) {
    return "This workspace's AI budget is used up, so the document cannot be indexed.";
  }
  return null;
}

export const MATCH_LABEL: Record<SearchHit["matched_by"][number], string> = {
  keyword: "Keyword",
  semantic: "Meaning",
};
