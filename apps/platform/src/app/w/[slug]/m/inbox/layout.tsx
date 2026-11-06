import type { ReactNode } from "react";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { inboxPath } from "@/lib/inbox";

import { CrmNav as SectionNav } from "../crm/crm-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function InboxLayout({ children, params }: Props) {
  const { slug } = await params;
  const path = inboxPath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "inbox" } } }),
    ),
    path,
  );
  const workspace = requireOk(await getWorkspace(slug), path);
  const sections = [{ href: inboxPath(slug, "conversations"), label: "Conversations" }];
  if (workspace.permissions.includes("inbox.manage")) {
    sections.push({ href: inboxPath(slug, "channels"), label: "Channels" });
  }
  sections.push({ href: inboxPath(slug, "suppressions"), label: "Blocked addresses" });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
        <SectionNav label="Inbox" sections={sections} />
      </div>
      {children}
    </div>
  );
}
