"use client";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@onyx/ui/components/breadcrumb";
import { Separator } from "@onyx/ui/components/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@onyx/ui/components/sidebar";
import { ThemeToggle } from "@onyx/ui/components/theme-toggle";
import { cn } from "@onyx/ui/lib/utils";
import {
  Bot,
  Building2,
  Contact,
  FileText,
  Gauge,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  Package,
  Send,
  Settings,
  ShieldCheck,
  ShoppingCart,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, type ReactNode } from "react";

import { isActive } from "@/lib/nav";

import { UserMenu } from "./user-menu";

// Icons are referenced by name so server components can describe navigation.
const ICONS = {
  overview: LayoutDashboard,
  crm: Contact,
  catalogue: Package,
  inbox: Inbox,
  quotations: FileText,
  orders: ShoppingCart,
  assistant: Bot,
  outbound: Send,
  settings: Settings,
  organizations: Building2,
  status: Gauge,
  admin: ShieldCheck,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;
export type NavItem = { href: string; label: string; icon: IconName; exact?: boolean };
export type NavGroup = { label?: string; items: NavItem[] };
export type Crumb = { label: string; href: string };

/** Breadcrumbs for `pathname`: every path prefix (from `rootHref`) that has a label. */
export function crumbsFor(
  pathname: string,
  rootHref: string,
  labels: Record<string, string>,
): Crumb[] {
  if (!isActive(pathname, rootHref)) return [];
  const rest = pathname.slice(rootHref.length).split("/").filter(Boolean);
  const hrefs = [rootHref, ...rest.map((_, i) => `${rootHref}/${rest.slice(0, i + 1).join("/")}`)];
  return hrefs.filter((h) => labels[h]).map((h) => ({ href: h, label: labels[h]! }));
}

type AppShellProps = {
  variant?: "workspace" | "admin";
  header: ReactNode;
  nav: NavGroup[];
  user: { displayName: string; email: string };
  rootHref: string;
  /** Labels for breadcrumb paths, e.g. {"/w/acme": "Acme", "/w/acme/settings": "Settings"}. */
  crumbLabels: Record<string, string>;
  defaultOpen?: boolean;
  children: ReactNode;
};

export function AppShell({
  variant = "workspace",
  header,
  nav,
  user,
  rootHref,
  crumbLabels,
  defaultOpen = true,
  children,
}: AppShellProps) {
  const pathname = usePathname();
  const admin = variant === "admin";
  const crumbs = crumbsFor(pathname, rootHref, crumbLabels);

  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <a
        href="#main"
        className="bg-background focus-visible:ring-ring sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus-visible:ring-2"
      >
        Skip to content
      </a>
      <Sidebar collapsible="icon" className={cn(admin && "border-brand border-r-2")}>
        <SidebarHeader>{header}</SidebarHeader>
        <SidebarContent>
          <nav aria-label={admin ? "Platform admin" : "Workspace"}>
            {nav.map((group, i) => (
              <SidebarGroup key={group.label ?? i}>
                {group.label ? <SidebarGroupLabel>{group.label}</SidebarGroupLabel> : null}
                <SidebarGroupContent>
                  <SidebarMenu>
                    {group.items.map((item) => {
                      const Icon = ICONS[item.icon];
                      const active = isActive(pathname, item.href, item.exact);
                      return (
                        <SidebarMenuItem key={item.href}>
                          <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
                            <Link href={item.href} aria-current={active ? "page" : undefined}>
                              <Icon aria-hidden />
                              <span>{item.label}</span>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            ))}
          </nav>
        </SidebarContent>
        <SidebarFooter>
          <UserMenu user={user} />
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        {admin ? (
          <div
            role="status"
            className="bg-brand text-brand-foreground px-4 py-1.5 text-center text-sm font-medium"
          >
            Platform admin · account metadata only · no tenant business data
          </div>
        ) : null}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" aria-label="Toggle navigation" />
          <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              {crumbs.map((crumb, i) => (
                <Fragment key={`${crumb.label}-${i}`}>
                  {i > 0 ? <BreadcrumbSeparator /> : null}
                  <BreadcrumbItem>
                    {i < crumbs.length - 1 ? (
                      <BreadcrumbLink asChild>
                        <Link href={crumb.href}>{crumb.label}</Link>
                      </BreadcrumbLink>
                    ) : (
                      <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                    )}
                  </BreadcrumbItem>
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
          <ThemeToggle className="ml-auto" />
        </header>
        <main id="main" tabIndex={-1} className="flex flex-1 flex-col gap-6 p-4 md:p-6">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
