import { Button } from "@onyx/ui/components/button";
import type { Metadata } from "next";
import Image from "next/image";

import { SiteFooter, SiteNav } from "@/components/sections";
import { site } from "@/content/site";
import {
  webDesignPackages,
  webDesignPath,
  webDesignProjects,
  type WebDesignPackageName,
} from "@/content/web-design";
import { siteEnv } from "@/lib/env";

import { EnquiryContacts } from "./campaign-contact";
import { EnquiryForm } from "./enquiry-form";

const title = "Web design and development in Malta";
const description =
  "Onyx Studio designs and builds websites, online shops, booking sites and custom web apps for Maltese businesses. Website packages from €300 including VAT.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: webDesignPath },
  openGraph: {
    title,
    description,
    url: webDesignPath,
    type: "website",
    siteName: site.name,
    locale: "en_MT",
  },
  twitter: { card: "summary_large_image", title, description },
};

const section = "mx-auto w-full max-w-6xl px-5 sm:px-8";
const heading = "text-3xl font-light tracking-tight sm:text-5xl";
const eyebrow = "text-brand font-mono text-xs tracking-[0.18em] uppercase";

const packageAccents = {
  Bronze: "[--package-accent:#bb8564]",
  Silver: "[--package-accent:#bdc4d5]",
  Gold: "[--package-accent:#e5bd64]",
  Onyx: "[--package-accent:var(--brand)]",
} satisfies Record<WebDesignPackageName, string>;

export default function WebDesignPage() {
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
        <section className="relative isolate overflow-hidden border-b border-white/10 pt-40 pb-20 sm:pt-48 sm:pb-28">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_85%_24%,color-mix(in_oklab,var(--brand)_20%,transparent),transparent_55%)]"
          />
          <div className={section}>
            <p className={eyebrow}>Onyx Studio · Malta</p>
            <h1 className="mt-6 max-w-4xl text-[clamp(2.9rem,8vw,6.75rem)] leading-[0.98] font-light tracking-[-0.065em]">
              Web design and development
              <span className="text-brand block">in Malta.</span>
            </h1>
            <p className="text-muted-foreground mt-8 max-w-xl text-lg leading-relaxed">
              From your first business website to an online shop or a custom web app, we handle the
              design, build and launch. We can write the copy, set up SEO and look after your site
              once it goes live.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild variant="brand" className="rounded-full px-6">
                <a href="#enquiry">Get a quote</a>
              </Button>
              <Button asChild variant="outline" className="rounded-full px-6">
                <a href="#packages">View packages</a>
              </Button>
            </div>
          </div>
        </section>

        <section
          id="packages"
          className={`${section} scroll-mt-28 py-16 sm:py-24`}
          aria-labelledby="packages-heading"
        >
          <div className="flex flex-wrap items-end justify-between gap-4">
            <h2 id="packages-heading" className={heading}>
              Website packages
            </h2>
            <p className="text-muted-foreground text-sm">
              One-off build prices. All prices include VAT.
            </p>
          </div>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {webDesignPackages.map(({ name, price, type, description, features }) => (
              <article
                key={name}
                className={`flex flex-col rounded-2xl border border-t-2 border-white/10 [border-top-color:var(--package-accent)] bg-white/[0.035] p-5 xl:p-6 ${packageAccents[name]}`}
              >
                <h3 className="text-xl font-medium">{name}</h3>
                <p className="mt-4 flex flex-wrap items-baseline gap-x-2">
                  <span className="text-muted-foreground text-sm">From</span>
                  <span className="text-3xl tracking-tight sm:text-4xl">{price}</span>
                </p>
                <p className="mt-5 font-medium">{type}</p>
                <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{description}</p>
                <ul className="text-muted-foreground mt-5 flex-1 list-disc space-y-2 border-t border-white/10 pt-5 pl-4 text-sm marker:text-[var(--brand)]">
                  {features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <Button asChild variant="outline" className="mt-6 w-full rounded-full">
                  <a href="#enquiry">Ask about {name}</a>
                </Button>
              </article>
            ))}
          </div>

          <div className="mt-6 grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 md:grid-cols-2">
            <article className="bg-background p-6 sm:p-8">
              <h3 className="text-xl font-medium">Website Care</h3>
              <p className="mt-3 text-3xl tracking-tight">
                €99<span className="text-muted-foreground text-base"> / year including VAT</span>
              </p>
              <p className="text-muted-foreground mt-3 max-w-md text-sm leading-relaxed">
                Hosting, backups, routine maintenance and security updates for standard sites.
                Content edits, domain renewals and care for more complex builds are quoted
                separately.
              </p>
            </article>
            <article className="bg-background p-6 sm:p-8">
              <h3 className="text-xl font-medium">AI and integrations</h3>
              <p className="text-muted-foreground mt-3 max-w-md text-sm leading-relaxed">
                Add an AI assistant that can answer common customer questions, or connect your site
                to the stock, calendars, inbox or tools your team already uses. We quote these
                options with your project.
              </p>
            </article>
          </div>
        </section>

        <section
          className="border-y border-white/10 bg-white/[0.025] py-16 sm:py-24"
          aria-labelledby="work-heading"
        >
          <div className={section}>
            <h2 id="work-heading" className={heading}>
              Clients we worked with
            </h2>
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {webDesignProjects.map(
                ({ name, type, description, screenshot, technologies, website, packageName }) => (
                  <article
                    key={name}
                    aria-label={name}
                    className={`portfolio-card bg-background flex flex-col overflow-hidden rounded-2xl border ${packageAccents[packageName]}`}
                  >
                    <div className="relative">
                      <a
                        href={website}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`${name} screenshot — visit website (opens in a new tab)`}
                        className="portfolio-image group focus-visible:outline-ring relative block aspect-[8/5] overflow-hidden border-b border-white/10 focus-visible:outline-2 focus-visible:-outline-offset-3"
                      >
                        <Image
                          src={screenshot.src}
                          alt={screenshot.alt}
                          width={1280}
                          height={screenshot.height}
                          sizes="(min-width: 1152px) 352px, (min-width: 768px) 32vw, 100vw"
                          className="portfolio-image-content h-full w-full object-contain"
                        />
                        <span
                          aria-hidden
                          className="pointer-events-none absolute top-3 right-3 z-10 rounded-full bg-black/85 px-3 py-1.5 text-xs text-white opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 motion-safe:transition-opacity"
                        >
                          Visit website ↗
                        </span>
                      </a>
                      <span className="portfolio-package pointer-events-none absolute right-3 bottom-3 z-10 rounded-full border bg-[#100d0b] px-3 py-1.5 text-xs font-semibold">
                        <span className="sr-only">Package: </span>
                        {packageName}
                      </span>
                    </div>
                    <div className="flex flex-1 flex-col p-5 sm:p-6">
                      <header>
                        <p className={eyebrow}>{type}</p>
                        <h3 className="mt-2 text-3xl font-light tracking-tight">{name}</h3>
                      </header>
                      <p className="text-muted-foreground mt-3 mb-5 flex-1 text-sm leading-relaxed">
                        {description}
                      </p>
                      <p className="text-muted-foreground border-t border-white/10 pt-4 text-xs">
                        Technologies
                      </p>
                      <ul
                        aria-label={`${name} technologies`}
                        className="mt-2 flex flex-wrap gap-1.5"
                      >
                        {technologies.map((technology) => (
                          <li
                            key={technology}
                            className="rounded-full border border-white/15 px-2.5 py-1 text-xs"
                          >
                            {technology}
                          </li>
                        ))}
                      </ul>
                      <a
                        href={website}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Visit website — ${name} (opens in a new tab)`}
                        className="text-brand focus-visible:outline-ring mt-5 inline-flex w-fit items-center gap-1.5 rounded-sm text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-4"
                      >
                        Visit website <span aria-hidden="true">↗</span>
                      </a>
                    </div>
                  </article>
                ),
              )}
            </div>
          </div>
        </section>

        <section
          id="enquiry"
          className={`${section} grid scroll-mt-28 gap-8 py-16 sm:py-24 lg:grid-cols-[2fr_3fr] lg:gap-12`}
          aria-labelledby="enquiry-heading"
        >
          <div>
            <h2 id="enquiry-heading" className={heading}>
              Get a quote
            </h2>
            <p className="text-muted-foreground mt-4 max-w-md leading-relaxed">
              Tell us what you’d like to build or improve, and what you want your customers to be
              able to do. We’ll get back to you to discuss the scope.
            </p>
            <EnquiryContacts />
          </div>
          <EnquiryForm />
        </section>
      </main>
      <SiteFooter platformUrl={platformUrl} innerPage />
    </>
  );
}
