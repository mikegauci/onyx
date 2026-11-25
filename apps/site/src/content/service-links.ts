import { webDesignPath } from "./web-design";

type ServiceLink = { title: string; slug: string };

export const newServiceLinks = [
  { title: "App Development", slug: "app-development" },
  { title: "Branding & Graphic Design", slug: "branding-graphic-design" },
  { title: "SEO", slug: "seo" },
  { title: "AI Automation", slug: "ai-automation" },
] as const satisfies readonly ServiceLink[];

export type ServiceSlug = (typeof newServiceLinks)[number]["slug"];

export function getServiceLink(slug: string) {
  return newServiceLinks.find((service) => service.slug === slug);
}

export function servicePath(slug: ServiceSlug) {
  return `/services/${slug}`;
}

export const serviceNavigation = [
  { title: "Web Design & Development", href: webDesignPath },
  ...newServiceLinks.map(({ title, slug }) => ({ title, href: servicePath(slug) })),
];
