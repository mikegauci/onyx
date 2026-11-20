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
  if (workspace.permissions.includes("catalogue.import")) {
    sections.push({ href: automotivePath(slug, "import"), label: "Import from website" });
  }
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Vehicles</h1>
        <SectionNav label="Vehicles" sections={sections} />
      </div>
      {children}
    </div>
  );
}
