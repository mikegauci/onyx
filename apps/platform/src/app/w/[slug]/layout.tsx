import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { AppShell, type IconName, type NavGroup } from "@/components/shell/app-shell";
import { WorkspaceSwitcher } from "@/components/shell/workspace-switcher";
import { getMe, getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { moduleLabel } from "@/lib/modules";
import { SETTINGS_SECTIONS, visibleSettings } from "@/lib/nav";

export const dynamic = "force-dynamic";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function WorkspaceLayout({ children, params }: Props) {
  const { slug } = await params;
  const base = `/w/${encodeURIComponent(slug)}`;
  const [meResult, workspaceResult] = await Promise.all([getMe(), getWorkspace(slug)]);
  const me = requireOk(meResult, base);
  const workspace = requireOk(workspaceResult, base);

  const settings = visibleSettings(workspace.permissions);
  const nav: NavGroup[] = [
    { items: [{ href: base, label: "Overview", icon: "overview", exact: true }] },
  ];
  if (workspace.modules.length > 0) {
    nav.push({
      label: "Modules",
      items: workspace.modules.map((key) => ({
        href: `${base}/m/${key}`,
        label: moduleLabel(key),
        icon: key in ICON_FOR_MODULE ? ICON_FOR_MODULE[key]! : "overview",
      })),
    });
  }
  if (settings.length > 0) {
    nav.push({ items: [{ href: `${base}/settings`, label: "Settings", icon: "settings" }] });
  }

  const crumbLabels: Record<string, string> = {
    [base]: workspace.name,
    [`${base}/settings`]: "Settings",
  };
  for (const key of workspace.modules) crumbLabels[`${base}/m/${key}`] = moduleLabel(key);
  for (const s of SETTINGS_SECTIONS) crumbLabels[`${base}/settings/${s.slug}`] = s.label;

  const sidebarOpen = (await cookies()).get("sidebar_state")?.value !== "false";

  return (
    <AppShell
      header={
        <WorkspaceSwitcher
          current={{ slug: workspace.slug, name: workspace.name, role: workspace.role }}
          workspaces={me.workspaces}
          isPlatformAdmin={me.is_platform_admin}
        />
      }
      nav={nav}
      user={{ displayName: me.user.display_name, email: me.user.email }}
      rootHref={base}
      crumbLabels={crumbLabels}
      defaultOpen={sidebarOpen}
    >
      {children}
    </AppShell>
  );
}

const ICON_FOR_MODULE: Record<string, IconName> = {
  crm: "crm",
  catalogue: "catalogue",
  inbox: "inbox",
  quotations: "quotations",
  orders: "orders",
  assistant: "assistant",
};
