/**
 * What the dashboard sends to Sentry (PR-027). Mirrors the API's scrubbing: no request
 * bodies, cookies, headers, query strings or user details; strings are scrubbed of email
 * addresses, phone numbers, bearer tokens and API keys. Off unless a DSN is set.
 */
export const REDACTED = "[redacted]";

const PATTERNS: RegExp[] = [
  /bearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /\b(?:sk|pk|re|whsec|sb|rk)_[A-Za-z0-9_-]{8,}\b/g,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  /\+?\d[\d\s().-]{7,}\d/g,
  // Invitation links carry a one-time token in the query string.
  /([?&]token=)[^&\s]+/g,
];

export function scrubText(value: string): string {
  return PATTERNS.reduce(
    (text, pattern) =>
      text.replace(pattern, (match, prefix?: string) =>
        typeof prefix === "string" && match.startsWith(prefix) ? `${prefix}${REDACTED}` : REDACTED,
      ),
    value,
  );
}

function scrub(value: unknown): unknown {
  if (typeof value === "string") return scrubText(value);
  if (Array.isArray(value)) return value.map(scrub);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrub(v)]));
  }
  return value;
}

type EventLike = { request?: object; user?: unknown; server_name?: string };

/** Sentry `beforeSend`: drops personal parts of the event and scrubs the rest. */
export function beforeSend<T extends EventLike>(event: T): T {
  const request = event.request as Record<string, unknown> | undefined;
  if (request) {
    for (const key of ["data", "cookies", "headers", "query_string", "env"]) delete request[key];
    if (typeof request.url === "string") request.url = request.url.split("?")[0];
  }
  delete event.user;
  delete event.server_name;
  const fields = event as Record<string, unknown>;
  for (const key of ["message", "exception", "breadcrumbs", "extra", "contexts"]) {
    if (key in fields) fields[key] = scrub(fields[key]);
  }
  return event;
}

export const SENTRY_OPTIONS = {
  sendDefaultPii: false,
  tracesSampleRate: 0,
  beforeSend,
} as const;
