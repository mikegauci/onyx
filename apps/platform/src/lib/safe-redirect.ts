/**
 * Resolves a post-sign-in redirect target (e.g. a `?next=` parameter) against the app origin.
 * Only same-origin paths are returned; anything else (absolute URLs to other hosts,
 * protocol-relative `//evil`, backslash tricks, `javascript:`) falls back to `fallback`.
 * Supabase's own redirect allow-list is configured separately (docs/deployment/environments.md).
 */
export function safeRedirect(
  target: string | null | undefined,
  appOrigin: string,
  fallback = "/dashboard",
): string {
  if (!target || !target.startsWith("/") || target.startsWith("//") || target.includes("\\")) {
    return fallback;
  }
  try {
    const resolved = new URL(target, appOrigin);
    if (resolved.origin !== new URL(appOrigin).origin) return fallback;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}
