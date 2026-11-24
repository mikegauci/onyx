"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

/**
 * Cycles through words in place, each sliding up out of a mask. Only the word moves: the slot
 * keeps a fixed size. Server HTML, no-JS and
 * reduced-motion visitors see the first word only. Hidden from assistive tech; the heading
 * carries a screen-reader version with the first word.
 */
export function RotatingWord({
  words,
  interval = 2600,
}: {
  words: readonly string[];
  interval?: number;
}) {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduce || words.length < 2) return;
    const id = window.setInterval(() => {
      if (!document.hidden) setIndex((i) => (i + 1) % words.length);
    }, interval);
    return () => window.clearInterval(id);
  }, [reduce, words.length, interval]);

  // Every word sits in the same grid cell, so the outgoing and incoming words overlap without
  // being taken out of flow: the slot's size never changes and nothing around it moves.
  // `contain` keeps the swap's layout and paint work inside the slot.
  return (
    <span className="-my-[0.12em] grid overflow-hidden py-[0.12em] whitespace-nowrap [contain:layout_paint]">
      <AnimatePresence initial={false}>
        <motion.span
          key={words[index]}
          className="text-brand col-start-1 row-start-1 block will-change-transform"
          initial={{ y: "105%", opacity: 0 }}
          animate={{ y: "0%", opacity: 1 }}
          exit={{ y: "-105%", opacity: 0 }}
          transition={{ duration: 0.7, ease: [0.2, 0.8, 0.1, 1] }}
        >
          {words[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
