"use client";

import { useEffect } from "react";

/**
 * One pointer listener for the page's hover effects:
 * - `.spotlight` elements get `--mx`/`--my` so CSS can draw a glow under the cursor;
 * - `[data-magnetic]` elements lean towards the cursor when it is close;
 * - `[data-cursor-glow]` (the footer) gets `--gx`/`--gy` for the wordmark gradient.
 * Mouse and pen only; magnetic movement is off for reduced motion.
 */
export function PointerEffects() {
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const fine = window.matchMedia("(pointer: fine)");
    if (!fine.matches) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let frame = 0;
    let last: PointerEvent | null = null;
    const magnets = () => Array.from(document.querySelectorAll<HTMLElement>("[data-magnetic]"));

    const apply = () => {
      frame = 0;
      const e = last;
      if (!e) return;

      const target = e.target instanceof Element ? e.target : null;
      const spot = target?.closest<HTMLElement>(".spotlight");
      if (spot) {
        const r = spot.getBoundingClientRect();
        spot.style.setProperty("--mx", `${e.clientX - r.left}px`);
        spot.style.setProperty("--my", `${e.clientY - r.top}px`);
      }

      const glow = target?.closest<HTMLElement>("[data-cursor-glow]");
      if (glow) {
        const r = glow.getBoundingClientRect();
        glow.style.setProperty("--gx", `${((e.clientX - r.left) / r.width) * 100}%`);
        glow.style.setProperty("--gy", `${((e.clientY - r.top) / r.height) * 100}%`);
      }

      if (!reduce) {
        for (const el of magnets()) {
          const r = el.getBoundingClientRect();
          const cx = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          const dx = e.clientX - cx;
          const dy = e.clientY - cy;
          const reach = Math.max(r.width, r.height) * 0.9;
          if (Math.abs(dx) < reach && Math.abs(dy) < reach) {
            el.style.transform = `translate(${dx * 0.22}px, ${dy * 0.3}px)`;
          } else if (el.style.transform) {
            el.style.transform = "";
          }
        }
      }
    };

    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      last = e;
      if (!frame) frame = requestAnimationFrame(apply);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return null;
}
