"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

/**
 * Cycles through words in place, each sliding up out of a mask. Server HTML, no-JS and
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

  return (
    <span className="relative -my-[0.12em] block overflow-hidden py-[0.12em] whitespace-nowrap">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={words[index]}
          className="text-brand block"
          initial={{ y: "105%", opacity: 0, filter: "blur(8px)" }}
          animate={{ y: "0%", opacity: 1, filter: "blur(0px)" }}
          exit={{ y: "-105%", opacity: 0, filter: "blur(8px)" }}
          transition={{ duration: 0.7, ease: [0.2, 0.8, 0.1, 1] }}
        >
          {words[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
