import "server-only";

import { platformEnv } from "./env";
import { getAccessToken } from "./supabase/server";

export type Role = "owner" | "admin" | "member";
export type WorkspaceSummary = { slug: string; name: string; role: Role };
export type Me = {
  user: { id: string; email: string; display_name: string };
  workspaces: WorkspaceSummary[];
};
export type Workspace = {
  slug: string;
  name: string;
  status: string;
  timezone: string;
  role: Role;
  modules: string[];
};

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: "unauthenticated" | "not_found" | "forbidden" | "unavailable" };

/**
 * Calls the Onyx API as the signed-in user. Hand-written until the generated OpenAPI client
 * (PR-006). Never throws for expected failures.
 */
export async function apiGet<T>(
  path: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResult<T>> {
  const token = await getAccessToken();
  if (!token) return { ok: false, status: "unauthenticated" };
  try {
    const response = await fetchImpl(new URL(path, platformEnv().apiUrl), {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return toResult<T>(response);
  } catch {
    return { ok: false, status: "unavailable" };
  }
}

export async function toResult<T>(response: Response): Promise<ApiResult<T>> {
  if (response.ok) return { ok: true, data: (await response.json()) as T };
  if (response.status === 401) return { ok: false, status: "unauthenticated" };
  if (response.status === 403) return { ok: false, status: "forbidden" };
  if (response.status === 404) return { ok: false, status: "not_found" };
  return { ok: false, status: "unavailable" };
}
