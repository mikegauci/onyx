"use client";

import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "motion/react";
import { useRef, useSyncExternalStore } from "react";

const noop = () => () => {};

function Word({
  word,
  progress,
  range,
}: {
  word: string;
  progress: MotionValue<number>;
  range: [number, number];
}) {
  const opacity = useTransform(progress, range, [0.18, 1]);
  return <motion.span style={{ opacity }}>{word} </motion.span>;
}

/**
 * A large statement whose words light up as it scrolls through the viewport. Server HTML and
 * reduced-motion visitors get the plain, fully visible text.
 */
export function WordReveal({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const reduce = useReducedMotion();
  // False during server render and hydration, true afterwards.
  const mounted = useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.45"] });

  const words = text.split(" ");
  const animate = mounted && !reduce;

  return (
    <p ref={ref} className={className}>
      {animate
        ? words.map((w, i) => (
            <Word
              key={i}
              word={w}
              progress={scrollYProgress}
              range={[i / words.length, (i + 1) / words.length]}
            />
          ))
        : text}
    </p>
  );
}
