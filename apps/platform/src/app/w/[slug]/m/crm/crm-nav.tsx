"use client";

import { cn } from "@onyx/ui/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive } from "@/lib/nav";

export function CrmNav({ sections }: { sections: { href: string; label: string }[] }) {
  const pathname = usePathname();
  return (
    <nav aria-label="CRM" className="border-b">
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
