"use client";

import { useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { systemScenarios } from "@/content/demos";
import { system } from "@/content/site";

const W = 1000;
const H = 520;
const CX = W / 2;
const CY = H / 2;

function rowY(i: number, n: number) {
  if (n <= 1) return H / 2;
  return 70 + (i * (H - 140)) / (n - 1);
}

function curve(x1: number, y1: number, x2: number, y2: number) {
  const mx = (x1 + x2) / 2;
  return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
}

const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

type Phase = "idle" | "in" | "think" | "out" | "done";

/**
 * Channels flow into Onyx, which connects them to the business. Click (or tab to) a channel to
 * play a fictional enquiry: it travels into the core, Onyx checks the business data, the
 * matching outputs light up and a reply is drafted below. While nobody has interacted, the
 * diagram plays each channel in turn when it is on screen. Reduced motion shows each result
 * without the travel animation. Phones get a stacked layout with the same panel.
 */
export function SystemDiagram() {
  const { inputs, outputs, core } = system;
  const reduce = useReducedMotion();
  const [active, setActive] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [typed, setTyped] = useState(0);
  const [touched, setTouched] = useState(false);

  const host = useRef<HTMLDivElement>(null);
  const paths = useRef(new Map<string, SVGPathElement>());
  const inDot = useRef<SVGCircleElement>(null);
  const outDots = useRef<(SVGCircleElement | null)[]>([]);
  const run = useRef(0);
  const frames = useRef<number[]>([]);
  const inView = useRef(false);

  const scenario = active ? systemScenarios[active] : undefined;

  const cancel = () => {
    run.current++;
    frames.current.forEach(cancelAnimationFrame);
    frames.current = [];
  };

  const travel = (
    path: SVGPathElement | undefined,
    dot: SVGCircleElement | null,
    ms: number,
    token: number,
  ) =>
    new Promise<void>((resolve) => {
      if (!path || !dot) return resolve();
      const len = path.getTotalLength();
      const t0 = performance.now();
      const step = (now: number) => {
        if (token !== run.current) return resolve();
        const p = Math.min(1, (now - t0) / ms);
        const pt = path.getPointAtLength(len * ease(p));
        dot.setAttribute("cx", String(pt.x));
        dot.setAttribute("cy", String(pt.y));
        dot.style.opacity = p < 1 ? "1" : "0";
        if (p < 1) frames.current.push(requestAnimationFrame(step));
        else resolve();
      };
      frames.current.push(requestAnimationFrame(step));
    });

  const wait = (ms: number, token: number) =>
    new Promise<boolean>((resolve) => window.setTimeout(() => resolve(token === run.current), ms));

  const play = useCallback(
    async (channel: string) => {
      cancel();
      const token = run.current;
      const sc = systemScenarios[channel];
      if (!sc) return;
      setActive(channel);
      setTyped(0);
      if (reduce) {
        setPhase("done");
        setTyped(sc.reply.length);
        return;
      }
      setPhase("in");
      await travel(paths.current.get(`in:${channel}`), inDot.current, 750, token);
      if (token !== run.current) return;
      setPhase("think");
      if (!(await wait(650, token))) return;
      setPhase("out");
      await Promise.all(
        sc.outputs.map((o, i) =>
          travel(paths.current.get(`out:${o}`), outDots.current[i] ?? null, 700, token),
        ),
      );
      if (token !== run.current) return;
      setPhase("done");
      // Type the reply out.
      let n = 0;
      const typeStep = () => {
        if (token !== run.current) return;
        n = Math.min(sc.reply.length, n + 3);
        setTyped(n);
        if (n < sc.reply.length) window.setTimeout(typeStep, 18);
      };
      typeStep();
    },
    [reduce],
  );

  // Autoplay through the channels while on screen, until the visitor picks one.
  useEffect(() => {
    if (touched || !host.current) return;
    let i = 0;
    const io = new IntersectionObserver(
      ([e]) => {
        const was = inView.current;
        inView.current = !!e?.isIntersecting;
        if (inView.current && !was) void play(inputs[i % inputs.length]!);
      },
      { threshold: 0.35 },
    );
    io.observe(host.current);
    const id = window.setInterval(() => {
      if (!inView.current || document.hidden) return;
      i++;
      void play(inputs[i % inputs.length]!);
    }, 7500);
    return () => {
      io.disconnect();
      window.clearInterval(id);
    };
  }, [touched, play, inputs]);

  useEffect(() => () => cancel(), []);

  const choose = (channel: string) => {
    setTouched(true);
    void play(channel);
  };
  const onKey = (e: KeyboardEvent, channel: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(channel);
    }
  };

  const lit = (o: string) =>
    !!scenario && (phase === "out" || phase === "done") && scenario.outputs.includes(o);

  return (
    <div ref={host} className={`system-wrap phase-${phase}`}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label={`${inputs.join(", ")} flow into ${core}, which connects to ${outputs.join(", ")}. Choose a channel to play an example.`}
        className="system-diagram hidden w-full md:block"
      >
        <defs>
          <radialGradient id="core-glow">
            <stop offset="0" stopColor="var(--brand)" stopOpacity="0.55" />
            <stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {inputs.map((label, i) => {
          const y = rowY(i, inputs.length);
          const d = curve(190, y, CX - 70, CY);
          const on = active === label;
          return (
            <g
              key={label}
              role="button"
              tabIndex={0}
              aria-pressed={on}
              aria-label={`Play a ${label} example`}
              onClick={() => choose(label)}
              onKeyDown={(e) => onKey(e, label)}
              className={`node node-input ${on ? "is-active" : ""}`}
              style={{ ["--d" as string]: `${i * 0.45}s` }}
            >
              <path
                d={d}
                className="track"
                ref={(el) => {
                  if (el) paths.current.set(`in:${label}`, el);
                }}
              />
              <path d={d} className="pulse" pathLength={1} />
              <rect x={20} y={y - 22} width={170} height={44} rx={22} className="pill" />
              <text x={105} y={y + 5} textAnchor="middle" className="label">
                {label}
              </text>
            </g>
          );
        })}

        {outputs.map((label, i) => {
          const y = rowY(i, outputs.length);
          const d = curve(CX + 70, CY, W - 210, y);
          return (
            <g
              key={label}
              className={`node node-output ${lit(label) ? "is-lit" : ""}`}
              style={{ ["--d" as string]: `${1.2 + i * 0.45}s` }}
            >
              <path
                d={d}
                className="track"
                ref={(el) => {
                  if (el) paths.current.set(`out:${label}`, el);
                }}
              />
              <path d={d} className="pulse" pathLength={1} />
              <rect x={W - 210} y={y - 22} width={190} height={44} rx={22} className="pill" />
              <text x={W - 115} y={y + 5} textAnchor="middle" className="label">
                {label}
              </text>
            </g>
          );
        })}

        <circle ref={inDot} r={7} className="travel-dot" style={{ opacity: 0 }} />
        {outputs.map((o, i) => (
          <circle
            key={o}
            ref={(el) => {
              outDots.current[i] = el;
            }}
            r={6}
            className="travel-dot"
            style={{ opacity: 0 }}
          />
        ))}

        <circle cx={CX} cy={CY} r={150} fill="url(#core-glow)" className="core-glow" />
        <circle cx={CX} cy={CY} r={70} className="core-ring" />
        <circle cx={CX} cy={CY} r={70} className="core-ring core-ring-2" />
        <circle cx={CX} cy={CY} r={62} className="core" />
        <circle cx={CX} cy={CY} r={62} className="core-think" pathLength={1} />
        <g aria-hidden>
          <rect
            x={CX - 11}
            y={CY - 30}
            width={22}
            height={22}
            rx={4}
            transform={`rotate(45 ${CX} ${CY - 19})`}
            className="core-mark"
          />
          <text x={CX} y={CY + 24} textAnchor="middle" className="core-label">
            {core.toLowerCase()}
          </text>
        </g>
      </svg>

      {/* Phones: stacked layout with the same interaction. */}
      <div className="grid gap-6 md:hidden">
        <ul aria-label="Channels" className="flex flex-wrap justify-center gap-2">
          {inputs.map((l) => (
            <li key={l}>
              <button
                type="button"
                aria-pressed={active === l}
                onClick={() => choose(l)}
                className={`focus-visible:ring-ring/60 rounded-full border px-3 py-1.5 text-sm transition-colors outline-none focus-visible:ring-[3px] ${
                  active === l
                    ? "border-brand bg-brand/15 text-brand"
                    : "border-white/10 bg-white/[0.04]"
                }`}
              >
                {l}
              </button>
            </li>
          ))}
        </ul>
        <div aria-hidden className="mx-auto flex flex-col items-center gap-2">
          <span className="h-8 w-px bg-gradient-to-b from-transparent to-[var(--brand)]" />
          <span
            className={`border-brand/60 bg-brand/10 flex size-24 flex-col items-center justify-center gap-2 rounded-full border transition-shadow ${
              phase === "think" ? "shadow-[0_0_40px_var(--brand)]" : ""
            }`}
          >
            <span className="bg-brand size-3.5 rotate-45 rounded-[3px]" />
            <span className="text-base">{core.toLowerCase()}</span>
          </span>
          <span className="h-8 w-px bg-gradient-to-b from-[var(--brand)] to-transparent" />
        </div>
        <ul aria-label="Connected to" className="flex flex-wrap justify-center gap-2">
          {outputs.map((l) => (
            <li
              key={l}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                lit(l) ? "border-brand bg-brand/15 text-brand" : "border-white/10 bg-white/[0.04]"
              }`}
            >
              {l}
            </li>
          ))}
        </ul>
      </div>

      <ScenarioPanel channel={active} phase={phase} typed={typed} announce={touched} />
    </div>
  );
}

function ScenarioPanel({
  channel,
  phase,
  typed,
  announce,
}: {
  channel: string | null;
  phase: Phase;
  typed: number;
  announce: boolean;
}) {
  const sc = channel ? systemScenarios[channel] : undefined;
  const showChecks = phase === "think" || phase === "out" || phase === "done";
  const showReply = phase === "done";

  return (
    <div
      aria-live={announce ? "polite" : "off"}
      className="mt-10 grid min-h-[13rem] gap-4 rounded-2xl border border-white/10 bg-white/[0.02] p-5 sm:p-6 md:grid-cols-[1fr_1fr_1.3fr]"
    >
      {sc && channel ? (
        <>
          <div key={`m-${channel}`} className="panel-in">
            <p className="text-muted-foreground font-mono text-[11px] tracking-widest uppercase">
              Incoming · {channel}
            </p>
            <p className="mt-3 rounded-2xl rounded-tl-sm bg-white/[0.06] px-4 py-3 text-sm">
              {sc.message}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground font-mono text-[11px] tracking-widest uppercase">
              Onyx checks
            </p>
            <ul className="mt-3 space-y-2 text-sm">
              {showChecks
                ? sc.checks.map((c, i) => (
                    <li
                      key={c}
                      className="panel-in flex gap-2"
                      style={{ animationDelay: `${i * 220}ms` }}
                    >
                      <span aria-hidden className="text-success">
                        ✓
                      </span>
                      <span className="text-foreground/85">{c}</span>
                    </li>
                  ))
                : null}
            </ul>
          </div>
          <div>
            <p className="text-muted-foreground flex items-center justify-between gap-2 font-mono text-[11px] tracking-widest uppercase">
              Drafted reply
              {showReply ? (
                <span
                  className={`panel-in rounded-full px-2 py-0.5 font-sans text-[10px] tracking-normal normal-case ${
                    sc.needsApproval ? "bg-brand/15 text-brand" : "bg-success/15 text-success"
                  }`}
                >
                  {sc.needsApproval ? "Waiting for staff approval" : "Sent automatically"}
                </span>
              ) : null}
            </p>
            {showReply ? (
              <p className="bg-brand/10 border-brand/20 mt-3 rounded-2xl rounded-tr-sm border px-4 py-3 text-sm">
                {sc.reply.slice(0, typed)}
                {typed < sc.reply.length ? <span className="caret" aria-hidden /> : null}
              </p>
            ) : (
              <p className="mt-3 flex h-11 items-center gap-1.5 px-1" aria-hidden>
                {phase !== "idle" ? <span className="typing-dots" /> : null}
              </p>
            )}
          </div>
        </>
      ) : (
        <p className="text-muted-foreground self-center text-sm md:col-span-3">
          Choose a channel to see how Onyx handles a typical enquiry.
        </p>
      )}
    </div>
  );
}
