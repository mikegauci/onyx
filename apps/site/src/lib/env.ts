import { publicUrl } from "./public-url";

/** Build-time environment for the public site. Validated in next.config.ts. */
export function siteEnv(env: NodeJS.ProcessEnv = process.env) {
  return {
    platformUrl: publicUrl(
      "NEXT_PUBLIC_PLATFORM_URL",
      env.NEXT_PUBLIC_PLATFORM_URL,
      "http://localhost:3001",
      env.VERCEL_ENV,
    ),
  };
}
