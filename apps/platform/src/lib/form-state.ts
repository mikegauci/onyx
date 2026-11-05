import type { MutationOutcome } from "./api-client";

/** Result of a server-action form, shown by the form and announced to screen readers. */
export type FormState = {
  status: "idle" | "ok" | "error";
  message?: string;
  fieldErrors?: Record<string, string>;
  requestId?: string;
};

export const IDLE: FormState = { status: "idle" };

/** Maps an API failure to a form state: field errors from `details`, a message by status. */
export function failureState(outcome: Extract<MutationOutcome<unknown>, { ok: false }>): FormState {
  const fieldErrors: Record<string, string> = {};
  for (const detail of outcome.error?.details ?? []) {
    const field = detail.loc.at(-1);
    if (typeof field === "string" && !(field in fieldErrors)) fieldErrors[field] = detail.msg;
  }
  const message =
    outcome.status === 403
      ? "You do not have permission to do this."
      : outcome.status === 422
        ? (outcome.error?.message ?? "Check the highlighted fields.")
        : outcome.status === 401
          ? "Your session has expired. Sign in again."
          : (outcome.error?.message ?? "The Onyx API is unavailable. Try again shortly.");
  return { status: "error", message, fieldErrors, requestId: outcome.requestId };
}

/** A trimmed text field, or null when blank (the API treats null as "clear"). */
export function optionalText(formData: FormData, name: string): string | null {
  const value = String(formData.get(name) ?? "").trim();
  return value === "" ? null : value;
}

export function text(formData: FormData, name: string): string {
  return String(formData.get(name) ?? "").trim();
}
