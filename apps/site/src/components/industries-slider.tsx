"use client";

import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { Industry } from "@/content/site";

function IndustryCard({
  industry,
  index,
  total,
}: {
  industry: Industry;
  index: number;
  total: number;
}) {
  return (
    <article
      aria-labelledby={`industry-${industry.slug}`}
      className="industry-card group relative flex w-[85vw] shrink-0 snap-start flex-col justify-between overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-6 sm:w-[28rem] sm:p-8 lg:min-h-[min(34rem,calc(100vh-10rem))] lg:w-[30rem]"
    >
      <span
        aria-hidden
        className="industry-glow pointer-events-none absolute -top-24 -right-24 size-72 rounded-full opacity-40 transition-opacity duration-500 group-hover:opacity-90"
      />
      <div className="relative">
        <p className="text-muted-foreground font-mono text-xs">
          {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </p>
        <h3
          id={`industry-${industry.slug}`}
          className="mt-6 text-3xl font-light tracking-tight sm:text-4xl"
        >
          {industry.name}
        </h3>
        <p className="mt-4 text-lg leading-snug text-balance">{industry.headline}</p>
        <p className="text-muted-foreground mt-3 text-sm">{industry.pain}</p>
      </div>
      <ul className="relative mt-8 space-y-2.5 border-t border-white/10 pt-6 text-sm">
        {industry.workflows.map((w) => (
          <li key={w} className="flex gap-3">
            <span aria-hidden className="bg-brand mt-[0.55em] size-1.5 shrink-0 rounded-full" />
            <span className="text-foreground/85">{w}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

function PinnedTrack({ children }: { children: ReactNode }) {
  const section = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const [distance, setDistance] = useState(0);

  useEffect(() => {
    const measure = () => {
      if (track.current) setDistance(Math.max(0, track.current.scrollWidth - window.innerWidth));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const { scrollYProgress } = useScroll({ target: section, offset: ["start start", "end end"] });
  const x = useTransform(scrollYProgress, [0, 1], [0, -distance]);
  const bar = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);

  return (
    <div ref={section} style={{ height: `calc(100vh + ${distance}px)` }} className="relative">
      <div className="sticky top-0 flex h-screen flex-col justify-center overflow-hidden">
        <motion.div
          ref={track}
          style={{ x }}
          className="flex w-max gap-6 pr-[8vw] pl-[max(2rem,calc((100vw-72rem)/2+2rem))]"
        >
          {children}
        </motion.div>
        <div className="mx-auto mt-10 w-full max-w-6xl px-8">
          <div className="h-px bg-white/10">
            <motion.div style={{ width: bar }} className="bg-brand h-px" />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Industries as a horizontal track. On wide screens with motion allowed, vertical scrolling
 * moves the track sideways while the section is pinned. Everywhere else (server HTML, phones,
 * reduced motion) it is a native swipeable row with scroll snapping.
 */
export function IndustriesSlider({ industries }: { industries: readonly Industry[] }) {
  const reduce = useReducedMotion();
  const [wide, setWide] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(min-width: 1024px) and (min-height: 640px)");
    const update = () => setWide(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const cards = industries.map((ind, i) => (
    <IndustryCard key={ind.slug} industry={ind} index={i} total={industries.length} />
  ));

  if (wide && !reduce) return <PinnedTrack>{cards}</PinnedTrack>;

  return (
    <div className="mx-auto max-w-6xl">
      <div
        role="region"
        aria-label="Industries, scroll sideways"
        tabIndex={0}
        className="focus-visible:ring-ring/60 [scrollbar-width:thin] overflow-x-auto rounded-2xl px-5 pb-4 outline-none focus-visible:ring-[3px] sm:px-8"
      >
        <div className="flex snap-x snap-mandatory gap-4">{cards}</div>
      </div>
    </div>
  );
}
