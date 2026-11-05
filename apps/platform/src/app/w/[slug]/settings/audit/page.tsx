import { Button } from "@onyx/ui/components/button";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { AuditTable } from "./audit-table";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ cursor?: string }>;
};

export default async function AuditLogPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const { cursor } = await searchParams;
  const path = `/w/${slug}/settings/audit`;
  const workspace = await workspaceWith(slug, "audit.read", path);
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/audit", {
        params: { path: { slug: workspace.slug }, query: { limit: 50, cursor } },
      }),
    ),
    path,
  );

  return (
    <section aria-labelledby="audit-heading" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="audit-heading" className="text-lg font-medium">
          Audit log
        </h2>
        <p className="text-muted-foreground text-sm">
          Who changed what in this workspace, newest first. Times are in {workspace.timezone}.
        </p>
      </div>
      <AuditTable entries={page.items} timezone={workspace.timezone} />
      <div className="flex gap-2">
        {cursor ? (
          <Button asChild variant="outline" size="sm">
            <Link href={path}>Newest</Link>
          </Button>
        ) : null}
        {page.next_cursor ? (
          <Button asChild variant="outline" size="sm">
            <Link href={`${path}?cursor=${encodeURIComponent(page.next_cursor)}`}>
              Older entries
            </Link>
          </Button>
        ) : null}
      </div>
    </section>
  );
}
