"use client";

import { Fragment, useEffect, useRef, useState, type ElementType } from "react";

/**
 * A heading whose words rise out of a mask, one after another, the first time it scrolls into
 * view. The server renders it fully visible; it is only hidden (armed) on the client when it
 * starts below the fold, so no-JS and reduced-motion visitors always see it.
 */
export function RevealHeading({
  as: Tag = "h2",
  id,
  text,
  className,
}: {
  as?: ElementType;
  id?: string;
  text: string;
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const [state, setState] = useState<"static" | "armed" | "shown">("static");

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof window.matchMedia !== "function") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e?.isIntersecting) {
          setState("shown");
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -12% 0px" },
    );
    // Arm on the next frame so the hidden state is never painted for headings already in view.
    const raf = requestAnimationFrame(() => {
      setState("armed");
      io.observe(el);
    });
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, []);

  const words = text.split(" ");
  return (
    <Tag
      ref={ref}
      id={id}
      className={`reveal-heading is-${state} ${className ?? ""}`}
      aria-label={text}
    >
      {words.map((w, i) => (
        <Fragment key={i}>
          <span aria-hidden className="rh-mask">
            <span className="rh-word" style={{ transitionDelay: `${i * 45}ms` }}>
              {w}
            </span>
          </span>
          {i < words.length - 1 ? " " : null}
        </Fragment>
      ))}
    </Tag>
  );
}
