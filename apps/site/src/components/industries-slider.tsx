"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { industryChats, type Msg } from "@/content/demos";
import type { Industry } from "@/content/site";

function ChatPreview({ messages, reduce }: { messages: Msg[]; reduce: boolean }) {
  // Messages appear one by one; Onyx shows a typing indicator before each of its replies.
  const [shown, setShown] = useState(reduce ? messages.length : 0);
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    if (reduce || shown >= messages.length) return;
    const next = messages[shown]!;
    const delay = shown === 0 ? 250 : 700;
    if (next.from !== "customer") {
      const t1 = window.setTimeout(() => setTyping(true), delay);
      const t2 = window.setTimeout(() => {
        setTyping(false);
        setShown((n) => n + 1);
      }, delay + 900);
      return () => {
        window.clearTimeout(t1);
        window.clearTimeout(t2);
      };
    }
    const t = window.setTimeout(() => setShown((n) => n + 1), delay);
    return () => window.clearTimeout(t);
  }, [shown, messages, reduce]);

  return (
    <ol aria-label="Example conversation" className="flex flex-col gap-2.5 text-sm">
      {messages.slice(0, shown).map((m, i) => (
        <li
          key={i}
          className={`chat-in max-w-[85%] rounded-2xl px-3.5 py-2.5 ${
            m.from === "customer"
              ? "self-start rounded-tl-sm bg-white/[0.07]"
              : m.from === "staff"
                ? "border-info/30 bg-info/10 self-end rounded-tr-sm border"
                : "bg-brand/15 border-brand/25 self-end rounded-tr-sm border"
          }`}
        >
          {m.from !== "customer" ? (
            <span className="text-muted-foreground mb-0.5 block text-[10px] tracking-wide uppercase">
              {m.from === "staff" ? "Staff" : "Onyx"}
            </span>
          ) : null}
          {m.text}
        </li>
      ))}
      {typing ? (
        <li aria-hidden className="bg-brand/15 self-end rounded-2xl rounded-tr-sm px-3.5 py-3">
          <span className="typing-dots" />
        </li>
      ) : null}
    </ol>
  );
}

function IndustryCard({
  industry,
  index,
  total,
}: {
  industry: Industry;
  index: number;
  total: number;
}) {
  const reduce = !!useReducedMotion();
  const [open, setOpen] = useState(false);
  const hoverTimer = useRef<number | undefined>(undefined);
  const chat = industryChats[industry.slug];

  // Mouse hover opens the conversation after a short pause; touch and keyboard use the button.
  const onEnter = (e: ReactPointerEvent) => {
    if (e.pointerType !== "mouse" || !chat) return;
    hoverTimer.current = window.setTimeout(() => setOpen(true), 350);
  };
  const onLeave = (e: ReactPointerEvent) => {
    if (e.pointerType !== "mouse") return;
    window.clearTimeout(hoverTimer.current);
    setOpen(false);
  };

  return (
    <article
      aria-labelledby={`industry-${industry.slug}`}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      className="industry-card spotlight group relative flex w-[85vw] shrink-0 snap-start flex-col justify-between overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-6 sm:w-[28rem] sm:p-8 lg:w-[26rem]"
    >
      <span
        aria-hidden
        className="industry-glow pointer-events-none absolute -top-24 -right-24 size-72 rounded-full opacity-40 transition-opacity duration-500 group-hover:opacity-90"
      />
      <div className={`relative transition-opacity duration-300 ${open ? "opacity-0" : ""}`}>
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
      <ul
        className={`relative mt-8 space-y-2.5 border-t border-white/10 pt-6 text-sm transition-opacity duration-300 ${
          open ? "opacity-0" : ""
        }`}
      >
        {industry.workflows.map((w) => (
          <li key={w} className="flex gap-3">
            <span aria-hidden className="bg-brand mt-[0.55em] size-1.5 shrink-0 rounded-full" />
            <span className="text-foreground/85">{w}</span>
          </li>
        ))}
      </ul>

      {chat ? (
        <>
          {open ? (
            <div className="bg-background/95 absolute inset-0 z-10 flex flex-col p-6 backdrop-blur-sm sm:p-8">
              <p className="text-muted-foreground flex items-center justify-between font-mono text-xs">
                <span>{industry.name}</span>
                <span>Example · fictional</span>
              </p>
              <div className="mt-6 flex-1 overflow-hidden">
                <ChatPreview messages={chat} reduce={reduce} />
              </div>
            </div>
          ) : null}
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="focus-visible:ring-ring/60 hover:text-brand relative z-20 mt-6 inline-flex items-center gap-2 self-start rounded-full text-xs outline-none focus-visible:ring-[3px]"
          >
            <span aria-hidden className="bg-brand inline-block size-1.5 rounded-full" />
            {open ? "Back to overview" : "See a conversation"}
          </button>
        </>
      ) : null}
    </article>
  );
}

/**
 * Industries as a horizontal row: swipe or trackpad-scroll sideways, drag with the mouse, use
 * the arrow buttons, or focus the row and use the arrow keys. Vertical page scrolling is never
 * hijacked. Works without JS as a plain scrollable row.
 */
export function IndustriesSlider({ industries }: { industries: readonly Industry[] }) {
  const row = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; left: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [edges, setEdges] = useState({ start: true, end: false });

  useEffect(() => {
    const el = row.current;
    if (!el) return;
    const update = () =>
      setEdges({
        start: el.scrollLeft <= 4,
        end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 4,
      });
    update();
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  const step = (dir: 1 | -1) => {
    const el = row.current;
    if (!el) return;
    const card = el.querySelector<HTMLElement>(".industry-card");
    const amount = card ? card.offsetWidth + 16 : el.clientWidth * 0.8;
    const smooth = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollBy({ left: dir * amount, behavior: smooth ? "smooth" : "auto" });
  };

  // Mouse drag only; touch and pens already scroll natively.
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== "mouse" || e.button !== 0 || !row.current) return;
    drag.current = { x: e.clientX, left: row.current.scrollLeft, moved: false };
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const el = row.current;
    if (!d || !el) return;
    const dx = e.clientX - d.x;
    if (!d.moved && Math.abs(dx) > 4) {
      d.moved = true;
      setDragging(true);
      el.setPointerCapture(e.pointerId);
    }
    if (d.moved) el.scrollLeft = d.left - dx;
  };
  const endDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current?.moved && row.current?.hasPointerCapture(e.pointerId)) {
      row.current.releasePointerCapture(e.pointerId);
    }
    drag.current = null;
    setDragging(false);
  };

  return (
    <div>
      <div
        ref={row}
        role="region"
        aria-label="Industries, scroll sideways"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={`focus-visible:ring-ring/60 scroll-px-[var(--edge)] [scrollbar-width:none] overflow-x-auto overscroll-x-contain px-[var(--edge)] pb-6 outline-none [--edge:max(1.25rem,calc((100vw-72rem)/2+2rem))] focus-visible:ring-[3px] focus-visible:ring-inset [&::-webkit-scrollbar]:hidden ${
          dragging ? "cursor-grabbing select-none" : "cursor-grab snap-x snap-mandatory"
        }`}
      >
        <div className="flex w-max gap-4">
          {industries.map((ind, i) => (
            <IndustryCard key={ind.slug} industry={ind} index={i} total={industries.length} />
          ))}
        </div>
      </div>
      <div className="mx-auto mt-4 flex max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
        <p className="text-muted-foreground text-xs">Drag, swipe or use the arrows</p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => step(-1)}
            disabled={edges.start}
            aria-label="Previous industries"
            className="focus-visible:ring-ring/60 hover:border-brand hover:text-brand flex size-11 items-center justify-center rounded-full border border-white/15 transition-colors outline-none focus-visible:ring-[3px] disabled:opacity-30 disabled:hover:border-white/15 disabled:hover:text-current"
          >
            ←
          </button>
          <button
            type="button"
            onClick={() => step(1)}
            disabled={edges.end}
            aria-label="Next industries"
            className="focus-visible:ring-ring/60 hover:border-brand hover:text-brand flex size-11 items-center justify-center rounded-full border border-white/15 transition-colors outline-none focus-visible:ring-[3px] disabled:opacity-30 disabled:hover:border-white/15 disabled:hover:text-current"
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
}
