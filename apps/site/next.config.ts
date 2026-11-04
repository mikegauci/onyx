import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@onyx/ui"],
  // CLAUDE.md is the single source of agent instructions; skip generated AGENTS.md.
  agentRules: false,
};

export default nextConfig;
