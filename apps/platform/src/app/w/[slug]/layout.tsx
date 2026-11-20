import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { AppShell, type IconName, type NavGroup } from "@/components/shell/app-shell";
import { WorkspaceSwitcher } from "@/components/shell/workspace-switcher";
import { getMe, getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { moduleLabel } from "@/lib/modules";
import { withApi } from "@/lib/api-client";
import { SETTINGS_SECTIONS, visibleSettings } from "@/lib/nav";
import { tasksLabel } from "@/lib/tasks";

import { SuspendedWorkspace } from "./suspended";

export const dynamic = "force-dynamic";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function WorkspaceLayout({ children, params }: Props) {
  const { slug } = await params;
  const base = `/w/${encodeURIComponent(slug)}`;
  const meResult = await getMe();
  const me = requireOk(meResult, base);
  // A suspended workspace refuses every request (403); say why instead of "not found".
  const listed = me.workspaces.find((w) => w.slug === slug);
  if (listed?.status === "suspended") {
    return <SuspendedWorkspace name={listed.name} hasOthers={me.workspaces.length > 1} />;
  }
  const workspace = requireOk(await getWorkspace(slug), base);
  // The open count is a convenience; a failure leaves the plain label.
  const tasks = workspace.permissions.includes("tasks.read")
    ? await withApi((api) => api.GET("/v1/w/{slug}/tasks", { params: { path: { slug } } }))
    : null;

  const settings = visibleSettings(workspace.permissions);
  const nav: NavGroup[] = [
    { items: [{ href: base, label: "Overview", icon: "overview", exact: true }] },
  ];
  if (tasks) {
    nav[0]!.items.push({
      href: `${base}/tasks`,
      label: tasksLabel(tasks.ok ? tasks.data.open_count : 0),
      icon: "tasks",
    });
  }
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
    [base]: workspace.display_name ?? workspace.name,
    [`${base}/settings`]: "Settings",
    [`${base}/tasks`]: "Tasks",
  };
  for (const key of workspace.modules) crumbLabels[`${base}/m/${key}`] = moduleLabel(key);
  for (const s of SETTINGS_SECTIONS) crumbLabels[`${base}/settings/${s.slug}`] = s.label;

  const sidebarOpen = (await cookies()).get("sidebar_state")?.value !== "false";

  return (
    <AppShell
      header={
        <WorkspaceSwitcher
          current={{
            slug: workspace.slug,
            name: workspace.display_name ?? workspace.name,
            role: workspace.role,
            brandColor: workspace.brand_color,
          }}
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
  outbound: "outbound",
};
