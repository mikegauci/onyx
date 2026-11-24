import type { MetadataRoute } from "next";

import { webDesignPath } from "@/content/web-design";
import { siteEnv } from "@/lib/env";

export default function sitemap(): MetadataRoute.Sitemap {
  const { siteUrl } = siteEnv();
  return [
    { url: `${siteUrl}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${siteUrl}${webDesignPath}`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
