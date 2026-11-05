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
    <nav aria-label={label} className="border-b">
      <ul className="-mb-px flex gap-4 overflow-x-auto">
        {sections.map((section) => {
          const active = isActive(pathname, section.href);
          return (
            <li key={section.href}>
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "focus-visible:ring-ring inline-block rounded-sm border-b-2 px-1 pb-2 text-sm font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:outline-none",
                  active
                    ? "border-brand text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
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
