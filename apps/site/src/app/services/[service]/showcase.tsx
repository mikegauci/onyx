import Image from "next/image";

import type { ServiceSlug } from "@/content/service-links";
import { webDesignProjects } from "@/content/web-design";

import styles from "./brand-composition.module.css";

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

  const seo = slug === "seo";
  const steps = seo
    ? [
        ["Find the gaps", "Audit pages and search visibility"],
        ["Plan the fixes", "Prioritise technical and local SEO"],
        ["Track progress", "Review search data and enquiries"],
      ]
    : [
        ["Enquiry arrives", "WhatsApp, email or web chat"],
        ["The assistant prepares a reply", "Uses your approved information"],
        ["Your team takes it from here", "Review or hand off when needed"],
      ];

  return (
    <div className="mx-auto w-full max-w-md rounded-3xl border border-white/10 bg-black/50 p-4 shadow-xl sm:p-6">
      <p className="text-muted-foreground border-b border-white/10 pb-4 font-mono text-xs tracking-[0.14em] uppercase">
        {seo ? "A typical SEO project" : "Example enquiry workflow"}
      </p>
      <ol className="mt-3 space-y-2.5">
        {steps.map(([title, description], index) => (
          <li
            key={title}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/4 px-3 py-3 sm:px-4"
          >
            <span
              aria-hidden
              className="text-brand bg-brand/10 grid size-8 shrink-0 place-items-center rounded-full font-mono text-xs"
            >
              {index + 1}
            </span>
            <div>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-muted-foreground mt-0.5 text-xs">{description}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
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
