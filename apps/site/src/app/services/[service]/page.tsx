import { Button } from "@onyx/ui/components/button";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteFooter, SiteNav } from "@/components/sections";
import {
  getServiceLink,
  newServiceLinks,
  serviceNavigation,
  servicePath,
  type ServiceSlug,
} from "@/content/service-links";
import { servicePages } from "@/content/service-pages";
import { site } from "@/content/site";
import { siteEnv } from "@/lib/env";

import { sendServiceEnquiry } from "../web-design-development/actions";
import { EnquiryContacts } from "../web-design-development/campaign-contact";
import { EnquiryForm } from "../web-design-development/enquiry-form";
import { BrandingWork, ServiceVisual } from "./showcase";

type PageProps = { params: Promise<{ service: string }> };

const section = "mx-auto w-full max-w-6xl px-5 sm:px-8";
const heading = "text-3xl font-light tracking-tight sm:text-5xl";
const eyebrow = "text-brand font-mono text-xs tracking-[0.18em] uppercase";

const accents: Record<ServiceSlug, string> = {
  "app-development": "bg-[radial-gradient(ellipse_at_83%_25%,#263519_0%,transparent_63%)]",
  "branding-graphic-design": "bg-[radial-gradient(ellipse_at_83%_25%,#37213d_0%,transparent_63%)]",
  seo: "bg-[radial-gradient(ellipse_at_83%_25%,#183143_0%,transparent_63%)]",
  "ai-automation": "bg-[radial-gradient(ellipse_at_83%_25%,#3c2316_0%,transparent_63%)]",
};

export const dynamicParams = false;

export function generateStaticParams() {
  return newServiceLinks.map(({ slug }) => ({ service: slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { service } = await params;
  const link = getServiceLink(service);
  if (!link) notFound();
  const { title, description } = servicePages[link.slug];
  const url = servicePath(link.slug);
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: { title, description, url, type: "website", siteName: site.name, locale: "en_MT" },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function ServicePage({ params }: PageProps) {
  const { service } = await params;
  const link = getServiceLink(service);
  if (!link) notFound();

  const { slug, title } = link;
  const content = servicePages[slug];
  const { platformUrl } = siteEnv();

  return (
    <>
      <a
        href="#main"
        className="bg-background focus:ring-ring/50 sr-only z-50 rounded-md px-4 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:ring-[3px]"
      >
        Skip to content
      </a>
      <SiteNav platformUrl={platformUrl} innerPage />
      <main id="main">
        <section className="relative isolate overflow-hidden border-b border-white/10 pt-32 pb-16 sm:pt-40 sm:pb-24">
          <div
            aria-hidden
            className={`pointer-events-none absolute inset-0 -z-10 ${accents[slug]}`}
          />
          <div
            className={`${section} grid items-center gap-12 lg:grid-cols-[1.12fr_1fr] lg:gap-10`}
          >
            <div>
              <p className={eyebrow}>{title} · Malta</p>
              <h1 className="mt-6 text-[clamp(2.9rem,7vw,5.6rem)] leading-[0.99] font-light tracking-[-0.065em]">
                {content.headline[0]}{" "}
                <span className="text-brand block">{content.headline[1]}</span>
              </h1>
              <p className="text-muted-foreground mt-6 max-w-xl text-lg leading-relaxed">
                {content.introduction}
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Button asChild variant="brand" className="rounded-full px-6">
                  <a href="#enquiry">Get a quote</a>
                </Button>
                <Button asChild variant="outline" className="rounded-full px-6">
                  <a href="#what-we-do">What we do</a>
                </Button>
              </div>
            </div>
            <ServiceVisual slug={slug} />
          </div>
        </section>

        <section
          id="what-we-do"
          aria-labelledby="offerings-heading"
          className={`${section} scroll-mt-28 py-16 sm:py-24`}
        >
          <h2 id="offerings-heading" className={heading}>
            What we do
          </h2>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {content.offerings.map(({ id, title, description, points }) => (
              <article
                id={id}
                key={id}
                className="scroll-mt-28 rounded-2xl border border-white/10 bg-white/4 p-5 sm:p-7"
              >
                <h3 className="text-xl font-medium">{title}</h3>
                <p className="text-muted-foreground mt-3 text-sm leading-relaxed">{description}</p>
                <ul className="text-muted-foreground mt-5 list-disc space-y-2 border-t border-white/10 pt-5 pl-4 text-sm marker:text-[var(--brand)]">
                  {points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>

        {slug === "app-development" && (
          <section aria-labelledby="pantrila-heading" className={`${section} pb-16 sm:pb-24`}>
            <div className="rounded-3xl border border-white/10 bg-[#162018] p-6 sm:p-10">
              <p className={eyebrow}>Selected project</p>
              <h2 id="pantrila-heading" className={`${heading} mt-4`}>
                Pantrila
              </h2>
              <p className="text-muted-foreground mt-4 max-w-2xl leading-relaxed">
                Pantrila helps people find recipes from ingredients they already have, plan meals
                and turn those plans into a shopping list. The project spans iOS, Android and a web
                app, with shared accounts and data across devices.
              </p>
              <a
                href="https://pantrila.com/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand mt-6 inline-block text-sm font-medium underline-offset-4 hover:underline focus-visible:underline"
              >
                Visit Pantrila <span aria-hidden>↗</span>
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </div>
          </section>
        )}

        {slug === "branding-graphic-design" && (
          <section aria-labelledby="branding-work-heading" className={`${section} pb-16 sm:pb-24`}>
            <h2 id="branding-work-heading" className={`${heading} mb-8`}>
              Branding in use
            </h2>
            <BrandingWork />
          </section>
        )}

        <section
          aria-labelledby="questions-heading"
          className="border-y border-white/10 bg-white/3"
        >
          <div className={`${section} grid gap-7 py-16 sm:py-20 lg:grid-cols-[2fr_3fr]`}>
            <h2 id="questions-heading" className={heading}>
              Frequently asked questions
            </h2>
            <div className="divide-y divide-white/10 border-y border-white/10">
              {content.faq.map(({ question, answer }) => (
                <details key={question} className="group px-1">
                  <summary className="focus-visible:ring-brand flex cursor-pointer list-none items-center justify-between gap-4 rounded-md py-4 font-medium focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
                    {question}
                    <span aria-hidden className="text-brand shrink-0 text-xl group-open:hidden">
                      +
                    </span>
                    <span
                      aria-hidden
                      className="text-brand hidden shrink-0 text-xl group-open:inline"
                    >
                      −
                    </span>
                  </summary>
                  <p className="text-muted-foreground pb-5 text-sm leading-relaxed sm:text-base">
                    {answer}
                  </p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section
          id="enquiry"
          aria-labelledby="enquiry-heading"
          className={`${section} grid scroll-mt-28 gap-8 py-16 sm:py-24 lg:grid-cols-[2fr_3fr] lg:gap-12`}
        >
          <div>
            <h2 id="enquiry-heading" className={heading}>
              Get a quote
            </h2>
            <p className="text-muted-foreground mt-4 max-w-md leading-relaxed">{content.enquiry}</p>
            <EnquiryContacts campaignAware={false} />
          </div>
          <EnquiryForm
            service={{ label: `${title} enquiry`, action: sendServiceEnquiry.bind(null, slug) }}
          />
        </section>

        <section
          aria-labelledby="related-heading"
          className={`${section} border-t border-white/10 pt-9 pb-16`}
        >
          <h2 id="related-heading" className="text-lg font-medium">
            Explore other services
          </h2>
          <ul className="text-muted-foreground mt-4 flex flex-wrap gap-x-5 gap-y-3 text-sm">
            {serviceNavigation
              .filter(({ href }) => href !== servicePath(slug))
              .map(({ href, title }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="hover:text-brand underline-offset-4 hover:underline focus-visible:underline"
                  >
                    {title}
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      </main>
      <SiteFooter platformUrl={platformUrl} innerPage />
    </>
  );
}
