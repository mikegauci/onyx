import type { NextConfig } from "next";

import { platformEnv } from "./src/lib/env";
import { securityHeaders } from "./src/lib/security-headers";
import { supabaseEnv } from "./src/lib/supabase/env";

// Fail the build early when a deployed build is missing or misconfigures its public URLs.
platformEnv();
supabaseEnv();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The Playwright suite builds into its own directory so it never clobbers `make dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  transpilePackages: ["@onyx/ui", "@onyx/api-client"],
  experimental: {
    // A 1 MB CSV plus its preview and row errors must fit in the confirmation action.
    serverActions: { bodySizeLimit: "2mb" },
  },
  // Root AGENTS.md owns project instructions; skip framework-generated agent rules.
  agentRules: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders(process.env.VERCEL_ENV) }];
  },
};

export default nextConfig;
