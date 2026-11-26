import Image from "next/image";

import type { ServiceSlug } from "@/content/service-links";
import { webDesignProjects } from "@/content/web-design";

import workflow from "./ai-composition.module.css";
import styles from "./brand-composition.module.css";
import search from "./seo-composition.module.css";

const branding = {
  "QTM Detailing": {
    title: "A performance-led identity",
    description: "A bold motorsport-inspired mark set against dark photography and vivid accents.",
  },
  MaltaGuns: {
    title: "An identity for a community",
    description:
      "A distinctive wordmark and an editorial presentation for a Maltese community platform.",
  },
  Pantrila: {
    title: "A recognisable app identity",
    description: "A chef-hat app icon and a green palette carried across the cooking experience.",
  },
} as const;

type BrandingProject = keyof typeof branding;

function AiArtwork() {
  return (
    <div
      role="img"
      aria-label="Example workflow. A WhatsApp booking request reaches an AI assistant, which checks the calendar, updates the CRM and sends a booking confirmation."
      className={workflow.composition}
    >
      <div aria-hidden="true" className={workflow.artwork}>
        <span className={workflow.orbits} />
        <span className={`${workflow.connector} ${workflow.incoming}`} />
        <span className={`${workflow.connector} ${workflow.toCalendar}`} />
        <span className={`${workflow.connector} ${workflow.toCrm}`} />
        <span className={`${workflow.connector} ${workflow.outgoing}`} />

        <div className={`${workflow.card} ${workflow.message}`}>
          <span className={`${workflow.icon} ${workflow.mint}`}>
            <svg viewBox="0 0 24 24">
              <path d="M21 11.5a9 9 0 0 1-9.5 9 9 9 0 0 1-3.8-.9L3 21l1.4-4.7a9 9 0 0 1 7.1-13.8A9 9 0 0 1 21 11.5Z" />
            </svg>
          </span>
          <span>
            <small>WhatsApp</small>
            <strong>Can I book Friday at 10:30?</strong>
          </span>
        </div>
        <div className={`${workflow.card} ${workflow.assistant}`}>
          <span className={`${workflow.icon} ${workflow.amber}`}>
            <svg viewBox="0 0 24 24">
              <path d="m9.5 2 1.9 5.6L17 9.5l-5.6 1.9L9.5 17l-1.9-5.6L2 9.5l5.6-1.9L9.5 2ZM19 13v8m-4-4h8" />
            </svg>
          </span>
          <strong>AI assistant</strong>
        </div>
        <div className={`${workflow.card} ${workflow.calendar}`}>
          <span className={`${workflow.icon} ${workflow.blue}`}>
            <svg viewBox="0 0 24 24">
              <rect x="3" y="5" width="18" height="16" rx="2" />
              <path d="M16 3v4M8 3v4M3 10h18m-13 5h2m4 0h2" />
            </svg>
          </span>
          Calendar
        </div>
        <div className={`${workflow.card} ${workflow.crm}`}>
          <span className={`${workflow.icon} ${workflow.violet}`}>
            <svg viewBox="0 0 24 24">
              <rect x="5" y="3" width="15" height="18" rx="2" />
              <path d="M3 7h3m-3 5h3m-3 5h3m3 1a4 4 0 0 1 8 0" />
              <circle cx="13" cy="10" r="2" />
            </svg>
          </span>
          CRM
        </div>
        <div className={`${workflow.card} ${workflow.confirmation}`}>
          <span className={`${workflow.icon} ${workflow.mint}`}>
            <svg viewBox="0 0 24 24">
              <path d="m5 12 4 4L19 6" />
            </svg>
          </span>
          <span>
            <strong>Booking confirmed</strong>
            <small>Friday, 10:30 am · Reply sent</small>
          </span>
        </div>
      </div>
    </div>
  );
}

function SeoArtwork() {
  return (
    <div
      role="img"
      aria-label="Illustrative search for a physiotherapist in Mosta showing a map pin and a clinic website result."
      className={search.composition}
    >
      <div aria-hidden="true" className={search.map}>
        <span className={search.street} />
        <span className={search.street} />
        <span className={search.street} />
        <span className={search.ring} />
      </div>
      <div aria-hidden="true" className={search.query}>
        <span className={search.magnifier} />
        <span className={search.queryTerm}>Physiotherapist in Mosta</span>
      </div>
      <div aria-hidden="true" className={search.location}>
        <span className={search.pin}>
          <span />
        </span>
        <span className={search.place}>Mosta</span>
      </div>
      <div aria-hidden="true" className={search.result}>
        <span className={search.resultIcon}>
          <span className={search.globe} />
        </span>
        <div className={search.resultCopy}>
          <span>Website result</span>
          <strong>Physiotherapy Clinic</strong>
          <span>Treatments and appointments</span>
        </div>
      </div>
    </div>
  );
}

export function ServiceVisual({ slug }: { slug: ServiceSlug }) {
  if (slug === "app-development") {
    return (
      <figure className="isolate mx-auto w-full max-w-md">
        <div className="flex items-center justify-center gap-2 sm:gap-5">
          <div className="w-[45%] rotate-[-6deg] rounded-[1.45rem] border border-white/20 bg-black p-1.5 shadow-2xl sm:rounded-4xl sm:p-2">
            <Image
              src="/portfolio/services/pantrila-assistant.webp"
              alt="Pantrila assistant suggesting recipes from ingredients already on hand."
              width={540}
              height={960}
              sizes="(max-width: 640px) 45vw, 220px"
              priority
              className="aspect-[9/16] w-full rounded-[1.05rem] object-cover object-top sm:rounded-3xl"
            />
          </div>
          <div className="mt-8 w-[43%] rotate-[7deg] rounded-[1.45rem] border border-white/20 bg-black p-1.5 shadow-2xl sm:rounded-4xl sm:p-2">
            <Image
              src="/portfolio/services/pantrila-plan.webp"
              alt="Pantrila meal planner organised by day."
              width={540}
              height={960}
              sizes="(max-width: 640px) 43vw, 210px"
              className="aspect-[9/16] w-full rounded-[1.05rem] object-cover object-top sm:rounded-3xl"
            />
          </div>
        </div>
        <figcaption className="text-muted-foreground mt-7 text-center text-xs">
          Pantrila · Mobile views of the web app
        </figcaption>
      </figure>
    );
  }

  if (slug === "branding-graphic-design") {
    return (
      <div aria-hidden className={styles.composition}>
        <span className={styles.aqua} />
        <span className={styles.violet} />
        <span className={styles.capital}>A</span>
        <span className={styles.outline}>a</span>
        <span className={styles.orange} />
        <span className={styles.lowercase}>a</span>
      </div>
    );
  }

  if (slug === "seo") {
    return <SeoArtwork />;
  }

  return <AiArtwork />;
}

export function BrandingWork() {
  const projects = webDesignProjects.filter(
    (project): project is Extract<(typeof webDesignProjects)[number], { name: BrandingProject }> =>
      Object.hasOwn(branding, project.name),
  );

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {projects.map(({ name, screenshot, website }) => (
        <article
          key={name}
          className="overflow-hidden rounded-2xl border border-white/10 bg-white/4"
        >
          <a
            href={website}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Visit ${name} (opens in a new tab)`}
            className="group focus-visible:ring-brand block overflow-hidden focus-visible:ring-2 focus-visible:ring-inset"
          >
            <Image
              src={screenshot.src}
              alt={screenshot.alt}
              width={1280}
              height={screenshot.height}
              sizes="(max-width: 767px) 96vw, 370px"
              className="aspect-[8/5] w-full object-cover object-top motion-safe:transition-transform motion-safe:duration-500 motion-safe:group-hover:scale-105"
            />
          </a>
          <div className="p-5">
            <h3 className="text-xl font-medium">{name}</h3>
            <p className="mt-3 text-sm font-medium">{branding[name].title}</p>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              {branding[name].description}
            </p>
          </div>
        </article>
      ))}
    </div>
  );
}
