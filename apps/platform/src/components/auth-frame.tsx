import { ThemeToggle } from "@onyx/ui/components/theme-toggle";
import { cn } from "@onyx/ui/lib/utils";
import type { ReactNode } from "react";

/**
 * Full-screen frame for pages outside a workspace (sign-in, workspace picker, invitations):
 * the onyx.mt look, with the wordmark, a soft orange glow and a faint grid.
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
      <header className="flex items-center justify-between px-6 py-5">
        <span className="flex items-center gap-2 text-lg font-light tracking-[-0.02em]">
          <span aria-hidden className="bg-brand size-2 rounded-full" />
          onyx
        </span>
        <ThemeToggle />
      </header>
      <main
        className={cn(
          "mx-auto flex w-full flex-1 flex-col justify-center gap-8 px-6 pb-24",
          width === "md" ? "max-w-md" : "max-w-xl",
        )}
      >
        {children}
      </main>
    </div>
  );
}
