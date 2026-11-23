import type { MetadataRoute } from "next";

import { siteEnv } from "@/lib/env";

export default function robots(): MetadataRoute.Robots {
  const { siteUrl, indexable } = siteEnv();
  if (!indexable) return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  };
}
