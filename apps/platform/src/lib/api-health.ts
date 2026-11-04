export type ApiHealth =
  { state: "ok"; service: string; version: string } | { state: "unreachable"; reason: string };

type HealthPayload = { status: string; service: string; version: string };

function isHealthPayload(value: unknown): value is HealthPayload {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.status === "string" && typeof v.service === "string" && typeof v.version === "string"
  );
}

/**
 * Server-side liveness probe of the Onyx API. Never throws: any failure maps to "unreachable"
 * so the dashboard can render a clear status instead of an error page.
 */
export async function getApiHealth(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = 2000,
): Promise<ApiHealth> {
  try {
    const response = await fetchImpl(new URL("/health", baseUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return { state: "unreachable", reason: `HTTP ${response.status}` };
    const body: unknown = await response.json();
    if (!isHealthPayload(body) || body.status !== "ok") {
      return { state: "unreachable", reason: "Unexpected response" };
    }
    return { state: "ok", service: body.service, version: body.version };
  } catch {
    return { state: "unreachable", reason: "No response" };
  }
}
