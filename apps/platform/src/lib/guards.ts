import "server-only";

import { notFound, redirect } from "next/navigation";

import type { ApiResult } from "./api-client";

export class ApiUnavailableError extends Error {
  constructor(readonly requestId?: string) {
    super("The Onyx API is unavailable.");
    this.name = "ApiUnavailableError";
  }
}

/**
 * The data of a successful API result. Otherwise: sign-in for 401, the not-found page for
 * 403/404 (never revealing whether a workspace exists), and the error boundary for the rest.
 */
export function requireOk<T>(result: ApiResult<T>, nextPath: string): T {
  if (result.ok) return result.data;
  if (result.status === "unauthenticated") {
    redirect(`/login?next=${encodeURIComponent(nextPath)}`);
  }
  if (result.status === "not_found" || result.status === "forbidden") notFound();
  throw new ApiUnavailableError(result.requestId);
}
