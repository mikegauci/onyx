import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { crmPath } from "@/lib/crm";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";

import { CrmNav } from "./crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function CrmLayout({ children, params }: Props) {
  const { slug } = await params;
  const path = crmPath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "crm" } } }),
    ),
    path,
  );
  const workspace = requireOk(await getWorkspace(slug), path);
  const sections = [
    { href: crmPath(slug, "leads"), label: "Leads" },
    { href: crmPath(slug, "contacts"), label: "Contacts" },
    { href: crmPath(slug, "customers"), label: "Customers" },
  ];
  if (workspace.permissions.includes("crm.import")) {
    sections.push({ href: crmPath(slug, "import"), label: "Import" });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">CRM</h1>
        <CrmNav sections={sections} />
      </div>
      {children}
    </div>
  );
}
