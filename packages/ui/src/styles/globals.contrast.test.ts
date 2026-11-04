// @vitest-environment node
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

/*
 * Guards the design tokens against accessibility regressions: every
 * text/background pair used by the shared components must meet WCAG 2.2
 * contrast (4.5:1 for text, 3:1 for focus rings and input borders) in both
 * light and dark themes.
 */

type Oklch = [l: number, c: number, h: number];

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`Missing ${selector} block`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]!.trim()]),
  );
}

function parseOklch(value: string): Oklch {
  const match = /^oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)$/.exec(value);
  if (!match) throw new Error(`Not an opaque oklch() colour: ${value}`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function luminance([l, c, h]: Oklch): number {
  const a = c * Math.cos((h * Math.PI) / 180);
  const b = c * Math.sin((h * Math.PI) / 180);
  const lms = [
    (l + 0.3963377774 * a + 0.2158037573 * b) ** 3,
    (l - 0.1055613458 * a - 0.0638541728 * b) ** 3,
    (l - 0.0894841775 * a - 1.291485548 * b) ** 3,
  ] as const;
  const rgb = [
    4.0767416621 * lms[0] - 3.3077115913 * lms[1] + 0.2309699292 * lms[2],
    -1.2684380046 * lms[0] + 2.6097574011 * lms[1] - 0.3413193965 * lms[2],
    -0.0041960863 * lms[0] - 0.7034186147 * lms[1] + 1.707614701 * lms[2],
  ].map((v) => Math.min(1, Math.max(0, v)));
  return 0.2126 * rgb[0]! + 0.7152 * rgb[1]! + 0.0722 * rgb[2]!;
}

function contrast(fg: string, bg: string): number {
  const [hi, lo] = [luminance(parseOklch(fg)), luminance(parseOklch(bg))].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const TEXT_PAIRS: [fg: string, bg: string][] = [
  ["foreground", "background"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["muted-foreground", "background"],
  ["muted-foreground", "muted"],
  ["muted-foreground", "card"],
  ["accent-foreground", "accent"],
  ["brand-foreground", "brand"],
  ["brand", "background"],
  ["destructive-foreground", "destructive"],
  ["destructive", "background"],
  ["success-foreground", "success"],
  ["success", "background"],
  ["warning-foreground", "warning"],
  ["warning", "background"],
  ["info-foreground", "info"],
  ["info", "background"],
  ["sidebar-foreground", "sidebar"],
  ["sidebar-primary-foreground", "sidebar-primary"],
  ["sidebar-accent-foreground", "sidebar-accent"],
];

const NON_TEXT_PAIRS: [fg: string, bg: string][] = [
  ["ring", "background"],
  ["input", "background"],
];

describe.each([
  ["light", block(":root")],
  ["dark", { ...block(":root"), ...block(".dark") }],
])("%s theme tokens", (_theme, tokens) => {
  it.each(TEXT_PAIRS)("%s on %s meets 4.5:1", (fg, bg) => {
    expect(contrast(tokens[fg]!, tokens[bg]!)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(NON_TEXT_PAIRS)("%s on %s meets 3:1", (fg, bg) => {
    expect(contrast(tokens[fg]!, tokens[bg]!)).toBeGreaterThanOrEqual(3);
  });
});

describe("contrast helper", () => {
  it("matches the known black-on-white ratio", () => {
    expect(contrast("oklch(0 0 0)", "oklch(1 0 0)")).toBeCloseTo(21, 0);
  });
});
