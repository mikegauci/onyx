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
                  "focus-visible:ring-ring block rounded-full px-3.5 py-2 text-sm whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:outline-none md:rounded-lg",
                  active
                    ? "bg-foreground/10 text-foreground font-medium md:shadow-[inset_2px_0_0_var(--brand)]"
                    : "text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground",
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
