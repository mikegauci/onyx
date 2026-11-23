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

/**
 * Channels flow into Onyx, which connects them to the business. Pulses travel along each path
 * (CSS, stopped under reduced motion); hovering a node highlights its path. Phones get a
 * stacked version instead of the wide SVG.
 */
export function SystemDiagram() {
  const { inputs, outputs, core } = system;
  return (
    <>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${inputs.join(", ")} flow into ${core}, which connects to ${outputs.join(", ")}.`}
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
          return (
            <g key={label} className="node" style={{ ["--d" as string]: `${i * 0.45}s` }}>
              <path d={d} className="track" />
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
            <g key={label} className="node" style={{ ["--d" as string]: `${1.2 + i * 0.45}s` }}>
              <path d={d} className="track" />
              <path d={d} className="pulse" pathLength={1} />
              <rect x={W - 210} y={y - 22} width={190} height={44} rx={22} className="pill" />
              <text x={W - 115} y={y + 5} textAnchor="middle" className="label">
                {label}
              </text>
            </g>
          );
        })}

        <circle cx={CX} cy={CY} r={150} fill="url(#core-glow)" />
        <circle cx={CX} cy={CY} r={70} className="core-ring" />
        <circle cx={CX} cy={CY} r={70} className="core-ring core-ring-2" />
        <circle cx={CX} cy={CY} r={62} className="core" />
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

      <div className="grid gap-6 md:hidden">
        <ul aria-label="Channels" className="flex flex-wrap justify-center gap-2">
          {inputs.map((l) => (
            <li
              key={l}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm"
            >
              {l}
            </li>
          ))}
        </ul>
        <div aria-hidden className="mx-auto flex flex-col items-center gap-2">
          <span className="h-8 w-px bg-gradient-to-b from-transparent to-[var(--brand)]" />
          <span className="border-brand/60 bg-brand/10 flex size-24 flex-col items-center justify-center gap-2 rounded-full border">
            <span className="bg-brand size-3.5 rotate-45 rounded-[3px]" />
            <span className="text-base">{core.toLowerCase()}</span>
          </span>
          <span className="h-8 w-px bg-gradient-to-b from-[var(--brand)] to-transparent" />
        </div>
        <ul aria-label="Connected to" className="flex flex-wrap justify-center gap-2">
          {outputs.map((l) => (
            <li
              key={l}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm"
            >
              {l}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
