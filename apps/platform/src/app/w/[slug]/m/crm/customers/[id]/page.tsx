import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Panel } from "@onyx/ui/components/page";
import Link from "next/link";

import { RecordHeader, RecordLayout } from "@/components/record";
import { withApi } from "@/lib/api-client";
import { crmPath } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { CustomerForm, ArchiveButton } from "../../_components/forms";
import { ActivitySection } from "../../_components/activity-section";
import { recordId, param, type SearchParams } from "../../data";
export default async function CustomerPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>;
  searchParams: SearchParams;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = crmPath(slug, "customers", id);
  const workspace = await workspaceWith(slug, "crm.read", path);
  const record = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/crm/customers/{customer_id}", {
        params: { path: { slug, customer_id: id } },
      }),
    ),
    path,
  );
  const canWrite = workspace.permissions.includes("crm.write");

  return (
    <div className="flex flex-col gap-6">
      <RecordHeader
        back={{ href: crmPath(slug, "customers"), label: "Back to customers" }}
        title={record.name}
        badges={record.archived_at ? <Badge variant="secondary">Archived customer</Badge> : null}
        meta={
          <>
            <span>{record.kind === "business" ? "Business" : "Individual"}</span>
            <span>{record.vat_number ?? "No VAT number"}</span>
          </>
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={`${crmPath(slug, "leads")}?customer_id=${id}`}>View related leads</Link>
          </Button>
        }
      />
      <RecordLayout
        main={
          <Panel title="Customer details" divided={false}>
            {canWrite ? (
              <CustomerForm slug={slug} customer={record} />
            ) : (
              <p className="text-sm whitespace-pre-wrap">{record.notes || "No notes."}</p>
            )}
            {workspace.permissions.includes("crm.archive") ? (
              <div className="mt-5 border-t pt-4">
                <ArchiveButton
                  slug={slug}
                  kind="customer"
                  id={id}
                  archived={!!record.archived_at}
                />
              </div>
            ) : null}
          </Panel>
        }
        aside={
          <ActivitySection
            slug={slug}
            subjectType="customer"
            id={id}
            timezone={workspace.timezone}
            canWrite={canWrite}
            cursor={param((await searchParams).cursor)}
          />
        }
      />
    </div>
  );
}
