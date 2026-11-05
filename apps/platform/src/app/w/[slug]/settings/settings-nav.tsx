"use client";

import { cn } from "@onyx/ui/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive } from "@/lib/nav";

type Props = { base: string; sections: { slug: string; label: string }[] };

export function SettingsNav({ base, sections }: Props) {
  const pathname = usePathname();
  return (
    <nav aria-label="Settings" className="md:w-48 md:shrink-0">
      <ul className="flex gap-1 overflow-x-auto md:flex-col">
        {sections.map((s) => {
          const href = `${base}/${s.slug}`;
          const active = isActive(pathname, href);
          return (
            <li key={s.slug}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "focus-visible:ring-ring block rounded-md px-3 py-2 text-sm whitespace-nowrap focus-visible:ring-2 focus-visible:outline-none",
                  active ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/50",
                )}
              >
                {s.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
