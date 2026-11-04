import type { NextConfig } from "next";

import { platformEnv } from "./src/lib/env";
import { securityHeaders } from "./src/lib/security-headers";
import { supabaseEnv } from "./src/lib/supabase/env";

// Fail the build early when a deployed build is missing or misconfigures its public URLs.
platformEnv();
supabaseEnv();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@onyx/ui"],
  // CLAUDE.md is the single source of agent instructions; skip generated AGENTS.md.
  agentRules: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders(process.env.VERCEL_ENV) }];
  },
};

export default nextConfig;
