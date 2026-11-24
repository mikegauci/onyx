import { OnyxMark } from "@onyx/ui/components/onyx-logo";
import type { SVGProps } from "react";

/** The Onyx mark with fixed colours, for image routes (icons, Open Graph) that have no CSS. */
export function HandoffMark(props: SVGProps<SVGSVGElement>) {
  return <OnyxMark light="#f4eee6" {...props} />;
}
