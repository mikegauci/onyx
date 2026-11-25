import { PageHeader } from "@onyx/ui/components/page";
import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";

import { CrmNav as SectionNav } from "../crm/crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function AutomotiveLayout({ children, params }: Props) {
  const { slug } = await params;
  const path = automotivePath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "automotive" } } }),
    ),
    path,
  );
  const workspace = requireOk(await getWorkspace(slug), path);
  const sections = [{ href: automotivePath(slug, "vehicles"), label: "Vehicles" }];
  if (workspace.permissions.includes("crm.read")) {
    sections.push({ href: automotivePath(slug, "matches"), label: "Matches" });
  }
  if (workspace.permissions.includes("catalogue.import")) {
    sections.push({ href: automotivePath(slug, "import"), label: "Import from website" });
  }
  if (workspace.permissions.includes("inbox.manage")) {
    sections.push({ href: automotivePath(slug, "alerts"), label: "Alert settings" });
  }
  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Module" title="Vehicles">
        <SectionNav label="Vehicles" sections={sections} />
      </PageHeader>
      {children}
    </div>
  );
}
