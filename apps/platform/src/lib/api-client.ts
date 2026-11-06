import "server-only";

import { type ApiClient, type ApiError, apiErrorOf, createApiClient } from "@onyx/api-client";

import { platformEnv } from "./env";
import { getAccessToken } from "./supabase/server";

export type { Me, Permission, Role, Workspace, WorkspaceSummary } from "@onyx/api-client";

export type ApiFailure = "unauthenticated" | "not_found" | "forbidden" | "unavailable";

export type ApiResult<T> =
  { ok: true; data: T } | { ok: false; status: ApiFailure; requestId?: string };

type CallResult<T> = { data?: T; error?: unknown; response: Response };

const TIMEOUT_MS = 5000;

export function newRequestId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

/**
 * Calls the Onyx API as the signed-in user through the generated, typed client.
 * Never throws for expected failures; the API stays the authority for every rule.
 *
 * @example withApi((api) => api.GET("/v1/w/{slug}", { params: { path: { slug } } }))
 */
/** Outcome of a mutation, keeping the API's error body (codes, field details). */
export type MutationOutcome<T> =
  { ok: true; data: T } | { ok: false; status: number; error?: ApiError; requestId: string };

/** Like `withApi`, but returns the standard error body so forms can show field errors. */
export async function mutateApi<T>(
  call: (api: ApiClient) => Promise<CallResult<T>>,
  fetchImpl: typeof fetch = fetch,
  timeoutMs: number = TIMEOUT_MS,
): Promise<MutationOutcome<T>> {
  const token = await getAccessToken();
  const requestId = newRequestId();
  if (!token) return { ok: false, status: 401, requestId };
  const api = createApiClient({
    baseUrl: platformEnv().apiUrl,
    accessToken: token,
    requestId,
    fetch: (input) =>
      fetchImpl(input, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) }),
  });
  try {
    const result = await call(api);
    // 204 No Content has no body; it is still a success.
    if (result.response.ok && (result.data !== undefined || result.response.status === 204)) {
      return { ok: true, data: result.data as T };
    }
    const error = apiErrorOf(result.error);
    return {
      ok: false,
      status: result.response.status,
      error,
      requestId: error?.request_id ?? requestId,
    };
  } catch {
    return { ok: false, status: 503, requestId };
  }
}

export async function withApi<T>(
  call: (api: ApiClient) => Promise<CallResult<T>>,
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResult<T>> {
  const token = await getAccessToken();
  if (!token) return { ok: false, status: "unauthenticated" };
  const requestId = newRequestId();
  const api = createApiClient({
    baseUrl: platformEnv().apiUrl,
    accessToken: token,
    requestId,
    fetch: (input) =>
      fetchImpl(input, { cache: "no-store", signal: AbortSignal.timeout(TIMEOUT_MS) }),
  });
  try {
    return toResult(await call(api), requestId);
  } catch {
    return { ok: false, status: "unavailable", requestId };
  }
}

export function toResult<T>(result: CallResult<T>, requestId?: string): ApiResult<T> {
  const { response } = result;
  if (response.ok && result.data !== undefined) return { ok: true, data: result.data };
  const id = apiErrorOf(result.error)?.request_id ?? requestId;
  const failure = (status: ApiFailure): ApiResult<T> =>
    id ? { ok: false, status, requestId: id } : { ok: false, status };
  if (response.status === 401) return failure("unauthenticated");
  if (response.status === 403) return failure("forbidden");
  if (response.status === 404) return failure("not_found");
  return failure("unavailable");
}
