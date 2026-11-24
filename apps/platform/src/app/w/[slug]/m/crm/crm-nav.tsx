"use client";

import { cn } from "@onyx/ui/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive } from "@/lib/nav";

/** Section tabs for a module (CRM, Catalogue, …), named for assistive technology by `label`. */
export function CrmNav({
  sections,
  label = "CRM",
}: {
  sections: { href: string; label: string }[];
  label?: string;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label={label} className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="bg-foreground/[0.03] inline-flex gap-1 rounded-full border p-1">
        {sections.map((section) => {
          const active = isActive(pathname, section.href);
          return (
            <li key={section.href}>
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "focus-visible:ring-ring inline-block rounded-full px-3.5 py-1.5 text-sm whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:outline-none",
                  active
                    ? "bg-foreground/10 text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {section.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
