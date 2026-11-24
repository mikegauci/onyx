"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { servicePreviews } from "@/content/demos";
import type { services as servicesData } from "@/content/site";

type Service = (typeof servicesData)[number];

function Preview({ kind }: { kind: "chat" | "checklist" | "browser" | "nodes" }) {
  switch (kind) {
    case "chat":
      return (
        <div className="flex flex-col gap-1.5 text-[11px]">
          <span className="prev-1 self-start rounded-xl rounded-tl-sm bg-white/10 px-2.5 py-1.5">
            Still available?
          </span>
          <span className="prev-2 bg-brand/25 self-end rounded-xl rounded-tr-sm px-2.5 py-1.5">
            Yes! Viewing tomorrow?
          </span>
          <span className="prev-3 self-start rounded-xl rounded-tl-sm bg-white/10 px-2.5 py-1.5">
            10:00 please
          </span>
        </div>
      );
    case "checklist":
      return (
        <ul className="space-y-1.5 text-[11px]">
          {["Reminder sent", "Docs received", "Follow-up booked"].map((t, i) => (
            <li key={t} className={`prev-${i + 1} flex items-center gap-2`}>
              <span className="bg-success/20 text-success flex size-4 items-center justify-center rounded-full text-[9px]">
                ✓
              </span>
              {t}
            </li>
          ))}
        </ul>
      );
    case "browser":
      return (
        <div className="overflow-hidden rounded-md border border-white/15">
          <div className="flex gap-1 border-b border-white/10 px-2 py-1.5">
            {[0, 1, 2].map((i) => (
              <span key={i} className="size-1.5 rounded-full bg-white/25" />
            ))}
          </div>
          <div className="space-y-1.5 p-2">
            <span className="prev-1 bg-brand/40 block h-2 w-2/3 rounded-full" />
            <span className="prev-2 block h-1.5 w-full rounded-full bg-white/15" />
            <span className="prev-3 grid grid-cols-3 gap-1">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-6 rounded bg-white/10" />
              ))}
            </span>
          </div>
        </div>
      );
    case "nodes":
      return (
        <svg viewBox="0 0 160 70" className="w-full" aria-hidden>
          {[
            [20, 15],
            [20, 55],
            [140, 15],
            [140, 55],
          ].map(([x, y], i) => (
            <g key={i}>
              <path
                d={`M${x},${y} L80,35`}
                className="prev-line"
                stroke="var(--brand)"
                strokeWidth="1.2"
              />
              <circle cx={x} cy={y} r="6" fill="oklch(1 0 0 / 15%)" />
            </g>
          ))}
          <circle cx="80" cy="35" r="10" fill="var(--brand)" className="prev-core" />
        </svg>
      );
  }
}

/**
 * Numbered service rows. On a mouse, a small preview card follows the cursor over each row,
 * hinting at what that service looks like. Hidden on touch, static under reduced motion.
 */
export function ServicesList({ services }: { services: readonly Service[] }) {
  const reduce = useReducedMotion();
  const [hovered, setHovered] = useState<number | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const pos = useRef({ x: 0, y: 0, tx: 0, ty: 0 });
  const frame = useRef(0);

  useEffect(() => {
    if (hovered === null) return;
    const tick = () => {
      const p = pos.current;
      p.x += (p.tx - p.x) * (reduce ? 1 : 0.18);
      p.y += (p.ty - p.y) * (reduce ? 1 : 0.18);
      if (card.current) {
        card.current.style.transform = `translate(${p.x}px, ${p.y}px)`;
        card.current.style.opacity = "1";
      }
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [hovered, reduce]);

  const onMove = (e: React.PointerEvent, i: number) => {
    if (e.pointerType !== "mouse") return;
    pos.current.tx = e.clientX + 24;
    pos.current.ty = e.clientY - 70;
    if (hovered !== i) {
      if (hovered === null) {
        pos.current.x = pos.current.tx;
        pos.current.y = pos.current.ty;
      }
      setHovered(i);
    }
  };

  const kind = hovered !== null ? servicePreviews[services[hovered]!.title] : undefined;

  return (
    <>
      <ol className="mt-16 border-t border-white/10" onPointerLeave={() => setHovered(null)}>
        {services.map((s, i) => (
          <li
            key={s.title}
            onPointerMove={(e) => onMove(e, i)}
            className="service-row group relative grid gap-4 border-b border-white/10 py-8 sm:grid-cols-[5rem_1fr_1fr] sm:items-baseline sm:py-10"
          >
            <span
              aria-hidden
              className="service-sheen pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
            />
            <span className="text-muted-foreground group-hover:text-brand relative font-mono text-sm transition-colors">
              0{i + 1}
            </span>
            <h3 className="relative text-3xl font-light tracking-tight transition-transform duration-500 group-hover:translate-x-2 sm:text-4xl">
              {s.title}
            </h3>
            <div className="relative">
              <p className="text-muted-foreground">{s.body}</p>
              <ul className="mt-4 flex flex-wrap gap-2" aria-label={`${s.title} examples`}>
                {s.tags.map((t) => (
                  <li key={t} className="rounded-full border border-white/10 px-2.5 py-1 text-xs">
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </li>
        ))}
      </ol>
      {kind ? (
        <div
          ref={card}
          aria-hidden
          style={{ opacity: 0 }}
          className="pointer-events-none fixed top-0 left-0 z-30 hidden w-48 rounded-xl border border-white/15 bg-black/80 p-3 shadow-2xl backdrop-blur-xl lg:block"
        >
          <div key={hovered} className="service-preview">
            <Preview kind={kind} />
          </div>
        </div>
      ) : null}
    </>
  );
}
