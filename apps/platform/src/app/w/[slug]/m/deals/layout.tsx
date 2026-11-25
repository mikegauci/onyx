import { PageHeader } from "@onyx/ui/components/page";
import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

import { CrmNav as SectionNav } from "../crm/crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function DealsLayout({ children, params }: Props) {
  const { slug } = await params;
  const path = dealsPath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "deals" } } }),
    ),
    path,
  );
  const workspace = requireOk(await getWorkspace(slug), path);
  const sections = [
    { href: dealsPath(slug, "board"), label: "Deals" },
    { href: dealsPath(slug, "finance"), label: "Finance" },
  ];
  if (workspace.permissions.includes("deals.manage")) {
    sections.push({ href: dealsPath(slug, "settings"), label: "Settings" });
  }
  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Module" title="Deals">
        <SectionNav label="Deals" sections={sections} />
      </PageHeader>
      {children}
    </div>
  );
}
