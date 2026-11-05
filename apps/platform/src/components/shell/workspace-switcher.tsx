"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@onyx/ui/components/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@onyx/ui/components/sidebar";
import { Check, ChevronsUpDown, ShieldCheck } from "lucide-react";
import Link from "next/link";

import type { WorkspaceSummary } from "@/lib/api-client";

type Props = {
  current: { slug: string; name: string; role: string } | null;
  workspaces: WorkspaceSummary[];
  isPlatformAdmin: boolean;
  /** Title shown when no workspace is current (the admin shell). */
  title?: string;
};

/** Switching navigates to /w/{slug}; the server re-checks membership on every request. */
export function WorkspaceSwitcher({ current, workspaces, isPlatformAdmin, title }: Props) {
  const label = current?.name ?? title ?? "Workspaces";
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" aria-label={`Switch workspace (current: ${label})`}>
              <span className="bg-brand text-brand-foreground flex aspect-square size-8 items-center justify-center rounded-lg text-sm font-semibold">
                {label.slice(0, 1).toUpperCase()}
              </span>
              <span className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{label}</span>
                {current ? (
                  <span className="text-muted-foreground truncate text-xs capitalize">
                    {current.role}
                  </span>
                ) : null}
              </span>
              <ChevronsUpDown aria-hidden className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64">
            <DropdownMenuLabel className="text-muted-foreground text-xs">
              Workspaces
            </DropdownMenuLabel>
            {workspaces.map((w) => (
              <DropdownMenuItem key={w.slug} asChild>
                <Link href={`/w/${w.slug}`}>
                  <span className="flex-1 truncate">{w.name}</span>
                  {w.slug === current?.slug ? <Check aria-label="Current" /> : null}
                </Link>
              </DropdownMenuItem>
            ))}
            {workspaces.length === 0 ? (
              <DropdownMenuItem disabled>No workspaces</DropdownMenuItem>
            ) : null}
            {isPlatformAdmin ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href="/admin">
                    <ShieldCheck aria-hidden />
                    Platform admin
                  </Link>
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
