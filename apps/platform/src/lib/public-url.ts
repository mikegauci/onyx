/** Thrown when a build-time URL setting is missing or unsafe for a deployed build. */
export class InvalidEnvError extends Error {
  override name = "InvalidEnvError";
}

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "0.0.0.0"]);

/**
 * Validates a public base URL (origin only). Deployed builds (`VERCEL_ENV` preview/production)
 * must use https on a non-local host; local builds fall back to `localDefault`.
 */
export function publicUrl(
  name: string,
  value: string | undefined,
  localDefault: string,
  vercelEnv: string | undefined,
): string {
  const deployed = vercelEnv === "preview" || vercelEnv === "production";
  const raw = value?.trim() || (deployed ? "" : localDefault);
  if (!raw) throw new InvalidEnvError(`${name} must be set for a ${vercelEnv} build.`);

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new InvalidEnvError(`${name} is not a valid URL.`);
  }
  if (url.pathname !== "/" || url.search || url.hash || url.username || url.password) {
    throw new InvalidEnvError(`${name} must be an origin (scheme://host[:port]) only.`);
  }
  if (deployed) {
    if (url.protocol !== "https:") throw new InvalidEnvError(`${name} must use https.`);
    if (LOCAL_HOSTS.has(url.hostname) || url.hostname.endsWith(".localhost")) {
      throw new InvalidEnvError(`${name} must not point at a local host.`);
    }
  }
  return url.origin;
}
