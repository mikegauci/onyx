import type { MetadataRoute } from "next";

import { siteEnv } from "@/lib/env";

export default function sitemap(): MetadataRoute.Sitemap {
  const { siteUrl } = siteEnv();
  return [{ url: `${siteUrl}/`, changeFrequency: "monthly", priority: 1 }];
}
