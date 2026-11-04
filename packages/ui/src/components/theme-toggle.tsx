"use client";

import { useTheme } from "next-themes";
import * as React from "react";

import { cn } from "../lib/utils";

const OPTIONS = [
  {
    value: "system",
    label: "System theme",
    icon: <path d="M4 5h16v11H4zM8 20h8M12 16v4" strokeLinecap="round" strokeLinejoin="round" />,
  },
  {
    value: "light",
    label: "Light theme",
    icon: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path
          d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
          strokeLinecap="round"
        />
      </>
    ),
  },
  {
    value: "dark",
    label: "Dark theme",
    icon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" strokeLinejoin="round" />,
  },
] as const;

const subscribe = () => () => {};

/** Three-way theme switch: follow the device, or force light or dark. */
function ThemeToggle({ className, ...props }: React.ComponentProps<"div">) {
  const { theme, setTheme } = useTheme();
  // The stored theme is only known in the browser; render a neutral state on the server.
  const mounted = React.useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const current = mounted ? (theme ?? "system") : undefined;

  return (
    <div
      role="group"
      aria-label="Colour theme"
      data-slot="theme-toggle"
      className={cn(
        "bg-background/80 inline-flex items-center gap-0.5 rounded-full border p-0.5 backdrop-blur",
        className,
      )}
      {...props}
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-label={option.label}
          aria-pressed={current === option.value}
          title={option.label}
          onClick={() => setTheme(option.value)}
          className="text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-foreground focus-visible:ring-ring/50 inline-flex size-7 items-center justify-center rounded-full transition-colors outline-none focus-visible:ring-[3px]"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            aria-hidden="true"
            className="size-4"
          >
            {option.icon}
          </svg>
        </button>
      ))}
    </div>
  );
}

export { ThemeToggle };
