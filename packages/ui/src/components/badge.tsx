import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "../lib/utils";

/*
 * Status colours must never be the only signal: always pair a badge colour with
 * its text label (and an icon where it helps), e.g. "Low stock", "AI draft".
 */
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:ring-[3px] focus-visible:ring-ring/50 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        // Soft tints, as on the onyx.mt site: a coloured label on a faint wash of the same hue.
        default: "border-transparent bg-foreground/10 text-foreground",
        secondary: "border-transparent bg-foreground/[0.07] text-muted-foreground",
        outline: "text-foreground",
        brand: "border-brand/25 bg-brand/15 text-brand",
        success: "border-success/25 bg-success/15 text-success",
        warning: "border-warning/25 bg-warning/15 text-warning",
        destructive: "border-destructive/25 bg-destructive/15 text-destructive",
        info: "border-info/25 bg-info/15 text-info",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

type BadgeProps = React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & {
    asChild?: boolean;
  };

function Badge({ className, variant, asChild = false, ...props }: BadgeProps) {
  const Comp = asChild ? Slot.Root : "span";

  return (
    <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
