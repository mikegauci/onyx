"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@onyx/ui/components/dropdown-menu";
import Link from "next/link";

import { serviceNavigation } from "@/content/service-links";

export function ServicesMenu({ overviewHref }: { overviewHref: string }) {
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/60 inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-2 text-xs font-medium transition-colors focus-visible:ring-[3px] focus-visible:outline-none sm:px-3 sm:text-sm">
        Services{" "}
        <span aria-hidden className="text-brand text-[0.7em]">
          ▾
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={10} className="min-w-56 border-white/15 p-1.5">
        <DropdownMenuItem asChild className="cursor-pointer p-2.5">
          <Link href={overviewHref}>All services</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {serviceNavigation.map(({ href, title }) => (
          <DropdownMenuItem key={href} asChild className="cursor-pointer p-2.5">
            <Link href={href}>{title}</Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
