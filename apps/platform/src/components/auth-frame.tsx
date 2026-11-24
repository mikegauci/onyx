import { LinesField } from "@onyx/ui/components/lines-field";
import { OnyxLogo } from "@onyx/ui/components/onyx-logo";
import { ThemeToggle } from "@onyx/ui/components/theme-toggle";
import { cn } from "@onyx/ui/lib/utils";
import Link from "next/link";
import type { ReactNode } from "react";

import { platformEnv } from "@/lib/env";

const footerLink =
  "hover:text-foreground focus-visible:ring-ring rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none";

/**
 * Full-screen frame for pages outside a workspace (sign-in, workspace picker, invitations):
 * the onyx.mt look, with the logo, a soft orange glow, a faint grid and (in dark mode, when
 * motion is allowed) the same moving lines as the onyx.mt hero.
 */
export function AuthFrame({
  children,
  width = "md",
}: {
  children: ReactNode;
  width?: "md" | "xl";
}) {
  return (
    <div className="relative isolate flex min-h-screen flex-col overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(60% 45% at 75% 0%, color-mix(in oklch, var(--brand) 18%, transparent), transparent 70%), radial-gradient(40% 35% at 10% 100%, color-mix(in oklch, var(--brand) 8%, transparent), transparent 70%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-60"
        style={{
          backgroundImage:
            "linear-gradient(to right, color-mix(in oklch, var(--foreground) 5%, transparent) 1px, transparent 1px), linear-gradient(to bottom, color-mix(in oklch, var(--foreground) 5%, transparent) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage: "radial-gradient(60% 60% at 50% 40%, black, transparent)",
        }}
      />
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 hidden dark:block">
        <LinesField />
      </div>
      <header className="flex items-center justify-between px-6 py-5">
        <OnyxLogo product="Platform" className="text-foreground" />
        <ThemeToggle />
      </header>
      <main
        className={cn(
          "mx-auto flex w-full flex-1 flex-col justify-center gap-8 px-6 pb-16",
          "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-3 motion-safe:duration-700",
          width === "md" ? "max-w-md" : "max-w-xl",
        )}
      >
        {children}
      </main>
      <footer className="text-muted-foreground flex flex-wrap items-center justify-center gap-x-6 gap-y-2 px-6 pb-6 text-xs">
        <a href={platformEnv().siteUrl} className={footerLink}>
          onyx.mt
        </a>
        <a href="mailto:info@onyx.mt" className={footerLink}>
          info@onyx.mt
        </a>
        <Link href="/dashboard" className={footerLink}>
          API status
        </Link>
      </footer>
    </div>
  );
}
