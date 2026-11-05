import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { quotationsPath } from "@/lib/quotations";

import { CrmNav as SectionNav } from "../crm/crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function QuotationsLayout({ children, params }: Props) {
  const { slug } = await params;
  const path = quotationsPath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "quotations" } } }),
    ),
    path,
  );
  const workspace = requireOk(await getWorkspace(slug), path);
  const sections = [{ href: quotationsPath(slug, "quotes"), label: "Quotes" }];
  if (workspace.permissions.includes("quotations.manage")) {
    sections.push({ href: quotationsPath(slug, "settings"), label: "Settings" });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Quotations</h1>
        <SectionNav label="Quotations" sections={sections} />
      </div>
      {children}
    </div>
  );
}
