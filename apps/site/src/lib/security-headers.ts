/** HTTP response headers applied to every route (see next.config.ts). */
export type Header = { key: string; value: string };

/**
 * @param vercelEnv `VERCEL_ENV` at build time: "production", "preview", "development" or unset.
 * HSTS is only sent from production; every non-production build is marked noindex.
 */
export function securityHeaders(vercelEnv: string | undefined): Header[] {
  const headers: Header[] = [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ];
  if (vercelEnv === "production") {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=63072000; includeSubDomains",
    });
  } else {
    headers.push({ key: "X-Robots-Tag", value: "noindex, nofollow" });
  }
  return headers;
}
