import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { WorkspaceSwitcher } from "@/components/shell/workspace-switcher";
import { getMe } from "@/lib/data";
import { requireOk } from "@/lib/guards";

export const dynamic = "force-dynamic";

/** Platform admin shell. Hidden (404) for everyone but platform admins; the API enforces it. */
export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = requireOk(await getMe(), "/admin");
  if (!me.is_platform_admin) notFound();

  return (
    <AppShell
      variant="admin"
      header={
        <WorkspaceSwitcher
          current={null}
          title="Platform admin"
          workspaces={me.workspaces}
          isPlatformAdmin
        />
      }
      nav={[
        {
          label: "Platform",
          items: [
            { href: "/admin", label: "Organisations", icon: "organizations", exact: true },
            { href: "/admin/status", label: "API status", icon: "status" },
          ],
        },
      ]}
      user={{ displayName: me.user.display_name, email: me.user.email }}
      rootHref="/admin"
      crumbLabels={{
        "/admin": "Platform admin",
        "/admin/status": "API status",
        "/admin/organizations": "Organisations",
      }}
    >
      {children}
    </AppShell>
  );
}
