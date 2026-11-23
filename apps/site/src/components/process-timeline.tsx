"use client";

import { motion, useMotionValueEvent, useReducedMotion, useScroll, useSpring } from "motion/react";
import { useRef, useState, useSyncExternalStore } from "react";

const noop = () => () => {};

import type { process as processData } from "@/content/site";

type Step = (typeof processData)[number];

/**
 * The four process steps with an orange line that draws as the section scrolls through the
 * viewport; each step's number lights up when the line reaches it. Without JS or with reduced
 * motion the line is full and every step is lit.
 */
export function ProcessTimeline({ steps }: { steps: readonly Step[] }) {
  const ref = useRef<HTMLOListElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.55"] });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 30 });
  const mounted = useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
  const [reached, setReached] = useState(-1);

  useMotionValueEvent(progress, "change", (v) => {
    if (reduce) return;
    setReached(Math.floor(v * steps.length + 0.15) - 1);
  });

  // Everything is lit in server HTML and for reduced motion; otherwise it follows the line.
  const lit = (i: number) => !mounted || !!reduce || i <= reached;

  return (
    <ol ref={ref} className="relative mt-16 grid gap-10 md:grid-cols-4 md:gap-6">
      {/* Track and fill: horizontal on desktop, vertical on phones. */}
      <span aria-hidden className="absolute top-0 left-0 hidden h-px w-full bg-white/15 md:block" />
      <motion.span
        aria-hidden
        style={reduce ? undefined : { scaleX: progress }}
        className="bg-brand absolute top-0 left-0 hidden h-px w-full origin-left md:block"
      />
      <span aria-hidden className="absolute top-0 left-0 h-full w-px bg-white/15 md:hidden" />
      <motion.span
        aria-hidden
        style={reduce ? undefined : { scaleY: progress }}
        className="bg-brand absolute top-0 left-0 h-full w-px origin-top md:hidden"
      />
      {steps.map((p, i) => (
        <li key={p.title} className="relative pt-6 pl-6 md:pl-0">
          <span
            aria-hidden
            className={`absolute -top-[5px] left-0 hidden size-[11px] rounded-full border transition-colors duration-500 md:block ${
              lit(i) ? "border-brand bg-brand" : "bg-background border-white/30"
            }`}
          />
          <p
            className={`text-[4.5rem] leading-none font-extralight tracking-tighter transition-colors duration-700 ${
              lit(i) ? "text-brand" : "text-white/15"
            }`}
          >
            0{i + 1}
          </p>
          <h3 className="mt-4 text-xl font-light">{p.title}</h3>
          <p className="text-muted-foreground mt-2 text-sm">{p.body}</p>
        </li>
      ))}
    </ol>
  );
}
