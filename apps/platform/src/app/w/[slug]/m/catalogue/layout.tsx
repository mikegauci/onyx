import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { cataloguePath } from "@/lib/catalogue";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";

import { CrmNav as SectionNav } from "../crm/crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function CatalogueLayout({ children, params }: Props) {
  const { slug } = await params;
  const path = cataloguePath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "catalogue" } } }),
    ),
    path,
  );
  const workspace = requireOk(await getWorkspace(slug), path);
  const sections = [
    { href: cataloguePath(slug, "products"), label: "Products" },
    { href: cataloguePath(slug, "imports"), label: "Import history" },
  ];
  if (workspace.permissions.includes("catalogue.import")) {
    sections.push({ href: cataloguePath(slug, "import"), label: "Import" });
  }
  if (workspace.permissions.includes("catalogue.manage")) {
    sections.push({ href: cataloguePath(slug, "settings"), label: "VAT and price lists" });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Catalogue</h1>
        <SectionNav label="Catalogue" sections={sections} />
      </div>
      {children}
    </div>
  );
}
