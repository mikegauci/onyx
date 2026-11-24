import type { SVGProps } from "react";

import { cn } from "../lib/utils";

/**
 * The Onyx mark: two interlocking brackets, one light and one orange. The light half follows
 * the text colour unless `light` is given, so it works on dark and light themes.
 */
export function OnyxMark({
  light = "currentColor",
  ...props
}: SVGProps<SVGSVGElement> & { light?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" {...props}>
      <path fill={light} d="M2 2h20v6H8v14H2Z" />
      <path fill="#fa762c" d="M30 10v20H10v-6h14V10Z" />
    </svg>
  );
}

/** Mark plus wordmark, e.g. "Onyx Studio" on onyx.mt and "Onyx Platform" on app.onyx.mt. */
export function OnyxLogo({
  product,
  className,
  markClassName,
  labelClassName,
}: {
  product: "Studio" | "Platform";
  className?: string;
  markClassName?: string;
  labelClassName?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-2.5 font-bold tracking-tight whitespace-nowrap",
        className,
      )}
    >
      <OnyxMark className={cn("size-5 shrink-0", markClassName)} />
      <span className={labelClassName}>Onyx {product}</span>
    </span>
  );
}
