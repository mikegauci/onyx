import { publicUrl } from "./public-url";

/** Build-time environment for the platform app. Validated in next.config.ts. */
export function platformEnv(env: NodeJS.ProcessEnv = process.env) {
  return {
    apiUrl: publicUrl(
      "NEXT_PUBLIC_API_URL",
      env.NEXT_PUBLIC_API_URL,
      "http://localhost:8000",
      env.VERCEL_ENV,
    ),
    siteUrl: publicUrl(
      "NEXT_PUBLIC_SITE_URL",
      env.NEXT_PUBLIC_SITE_URL,
      "http://localhost:3000",
      env.VERCEL_ENV,
    ),
    appUrl: publicUrl(
      "NEXT_PUBLIC_APP_URL",
      env.NEXT_PUBLIC_APP_URL,
      "http://localhost:3001",
      env.VERCEL_ENV,
    ),
  };
}
