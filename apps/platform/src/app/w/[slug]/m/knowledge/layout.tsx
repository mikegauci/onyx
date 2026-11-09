import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { knowledgePath } from "@/lib/knowledge";

import { CrmNav as SectionNav } from "../crm/crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function KnowledgeLayout({ children, params }: Props) {
  const { slug } = await params;
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "knowledge" } } }),
    ),
    knowledgePath(slug),
  );
  const sections = [
    { href: knowledgePath(slug, "documents"), label: "Documents" },
    { href: knowledgePath(slug, "search"), label: "Search" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Knowledge</h1>
        <SectionNav label="Knowledge" sections={sections} />
      </div>
      {children}
    </div>
  );
}
