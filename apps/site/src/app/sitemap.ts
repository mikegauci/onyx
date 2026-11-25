import type { MetadataRoute } from "next";

import { serviceNavigation } from "@/content/service-links";
import { siteEnv } from "@/lib/env";

export default function sitemap(): MetadataRoute.Sitemap {
  const { siteUrl } = siteEnv();
  return [
    { url: `${siteUrl}/`, changeFrequency: "monthly", priority: 1 },
    ...serviceNavigation.map(({ href }) => ({
      url: `${siteUrl}${href}`,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
