import { publicUrl } from "./public-url";

/** Build-time environment for the public site. Validated in next.config.ts. */
export function siteEnv(env: NodeJS.ProcessEnv = process.env) {
  // The site's own canonical origin (metadata, sitemap, robots). Production sets it explicitly;
  // previews fall back to the project's production domain, which Vercel always provides.
  const productionHost = env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
  const siteUrlValue =
    env.NEXT_PUBLIC_SITE_URL?.trim() || (productionHost ? `https://${productionHost}` : undefined);

  return {
    platformUrl: publicUrl(
      "NEXT_PUBLIC_PLATFORM_URL",
      env.NEXT_PUBLIC_PLATFORM_URL,
      "http://localhost:3001",
      env.VERCEL_ENV,
    ),
    siteUrl: publicUrl(
      "NEXT_PUBLIC_SITE_URL",
      siteUrlValue,
      "http://localhost:3000",
      env.VERCEL_ENV,
    ),
    /** Only production builds may be indexed by search engines. */
    indexable: env.VERCEL_ENV === "production",
  };
}
