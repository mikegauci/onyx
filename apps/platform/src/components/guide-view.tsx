import { Eyebrow } from "@onyx/ui/components/page";
import Image from "next/image";

import type { Guide } from "@/lib/guides";

/** One guide as a readable, printable page (PR-018). The same content feeds the PDFs. */
export function GuideView({ guide }: { guide: Guide }) {
  return (
    <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
      <nav
        aria-label="On this page"
        className="lg:sticky lg:top-20 lg:w-60 lg:shrink-0 print:hidden"
      >
        <Eyebrow className="mb-3">On this page</Eyebrow>
        <ol className="flex flex-col gap-1 text-sm">
          {guide.sections.map((s, i) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className="text-muted-foreground hover:text-foreground focus-visible:ring-ring block rounded-md px-2 py-1 focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="font-mono text-xs tabular-nums">{i + 1}.</span> {s.title}
              </a>
            </li>
          ))}
        </ol>
      </nav>
      <div className="flex max-w-3xl min-w-0 flex-1 flex-col gap-6">
        {guide.sections.map((s, i) => (
          <section
            key={s.id}
            id={s.id}
            aria-labelledby={`${s.id}-heading`}
            className="bg-card flex scroll-mt-20 flex-col gap-3 rounded-2xl border p-5 sm:p-6"
          >
            <h2 id={`${s.id}-heading`} className="text-lg font-medium tracking-tight">
              <span className="text-muted-foreground font-mono text-sm tabular-nums">{i + 1}.</span>{" "}
              {s.title}
            </h2>
            {s.audience ? (
              <p className="text-muted-foreground font-mono text-[11px] tracking-[0.12em] uppercase">
                For {s.audience.toLowerCase()}
              </p>
            ) : null}
            {s.intro ? <p className="text-sm leading-relaxed">{s.intro}</p> : null}
            {s.steps ? (
              <ol className="marker:text-brand flex list-decimal flex-col gap-2 pl-5 text-sm leading-relaxed">
                {s.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            ) : null}
            {s.points ? (
              <ul className="marker:text-foreground/30 flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed">
                {s.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            ) : null}
            {s.tip ? (
              <p className="border-brand/30 bg-brand/[0.05] rounded-xl border px-4 py-3 text-sm">
                <strong className="font-medium">Tip:</strong> {s.tip}
              </p>
            ) : null}
            {s.image ? (
              <figure className="flex flex-col gap-2">
                <Image
                  src={s.image.src}
                  alt={s.image.alt}
                  width={1440}
                  height={900}
                  className="rounded-xl border"
                  sizes="(min-width: 1024px) 768px, 100vw"
                />
                {s.image.caption ? (
                  <figcaption className="text-muted-foreground text-xs">
                    {s.image.caption}
                  </figcaption>
                ) : null}
              </figure>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}
