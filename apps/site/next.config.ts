import type { NextConfig } from "next";

import { siteEnv } from "./src/lib/env";
import { securityHeaders } from "./src/lib/security-headers";

// Fail the build early when a deployed build is missing or misconfigures its public URLs.
siteEnv();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@onyx/ui"],
  // Root AGENTS.md owns project instructions; skip framework-generated agent rules.
  agentRules: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders(process.env.VERCEL_ENV) }];
  },
};

export default nextConfig;
