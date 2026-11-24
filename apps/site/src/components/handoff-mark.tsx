import type { SVGProps } from "react";

export function HandoffMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" {...props}>
      <path fill="#f4eee6" d="M2 2h20v6H8v14H2Z" />
      <path fill="#fa762c" d="M30 10v20H10v-6h14V10Z" />
    </svg>
  );
}
