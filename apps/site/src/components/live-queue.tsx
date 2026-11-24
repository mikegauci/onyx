"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { liveQueue, queueStates } from "@/content/demos";

type Row = { id: number; item: number; state: number };

const TONE: Record<(typeof queueStates)[number], string> = {
  Drafting: "bg-white/10 text-foreground/70",
  "Draft ready": "bg-success/15 text-success",
  Approved: "bg-info/15 text-info",
  Sent: "bg-brand/15 text-brand",
};

// Deterministic first render so server and client HTML match.
const INITIAL: Row[] = [
  { id: 2, item: 2, state: 1 },
  { id: 1, item: 1, state: 2 },
  { id: 0, item: 0, state: 3 },
];

/**
 * The hero's approval queue, alive: a new enquiry arrives every few seconds and each row moves
 * Drafting → Draft ready → Approved → Sent. Pauses off-screen and in hidden tabs; static for
 * reduced motion and without JS.
 */
export function LiveQueue() {
  const reduce = useReducedMotion();
  const [rows, setRows] = useState<Row[]>(INITIAL);
  const host = useRef<HTMLDivElement>(null);
  const visible = useRef(true);

  useEffect(() => {
    if (reduce || !host.current) return;
    const io = new IntersectionObserver(([e]) => {
      visible.current = !!e?.isIntersecting;
    });
    io.observe(host.current);
    let next = INITIAL.length;
    const id = window.setInterval(() => {
      if (!visible.current || document.hidden) return;
      const fresh: Row = { id: next, item: next % liveQueue.length, state: 0 };
      next++;
      setRows((current) => {
        const advanced = current.map((r) => ({
          ...r,
          state: Math.min(r.state + 1, queueStates.length - 1),
        }));
        return [fresh, ...advanced].slice(0, 3);
      });
    }, 2600);
    return () => {
      window.clearInterval(id);
      io.disconnect();
    };
  }, [reduce]);

  return (
    <div ref={host}>
      {/* Fixed height: rows swap every few seconds and the hero text next to it must not move. */}
      <ul className="h-[194px] divide-y divide-white/10 overflow-hidden" aria-hidden>
        <AnimatePresence initial={false} mode="popLayout">
          {rows.map((row) => {
            const q = liveQueue[row.item]!;
            const state = queueStates[row.state]!;
            return (
              <motion.li
                key={row.id}
                layout={!reduce}
                initial={{ opacity: 0, y: -16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, transition: { duration: 0.2 } }}
                transition={{ duration: 0.45, ease: [0.2, 0.8, 0.2, 1] }}
                className="flex h-16 items-center justify-between gap-3 px-4"
              >
                <span className="min-w-0">
                  <span className="text-muted-foreground block text-[11px]">{q.channel}</span>
                  <span className="block truncate text-sm">“{q.text}”</span>
                </span>
                <motion.span
                  key={state}
                  initial={reduce ? false : { opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${TONE[state]}`}
                >
                  {state === "Drafting" ? (
                    <span className="inline-flex items-center gap-1">
                      Drafting
                      <span className="typing-dots" />
                    </span>
                  ) : (
                    state
                  )}
                </motion.span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
    </div>
  );
}
