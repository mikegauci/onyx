import { Panel } from "@onyx/ui/components/page";
import Link from "next/link";
import { Badge } from "@onyx/ui/components/badge";
import { RecordHeader, RecordLayout } from "@/components/record";
import { withApi } from "@/lib/api-client";
import { crmPath, STATUS_LABEL, STATUS_VARIANT } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { ArchiveButton, LeadEditForm, LeadStatusForm } from "../../_components/forms";
import { ActivitySection } from "../../_components/activity-section";
import { recordId, param, type SearchParams } from "../../data";
export default async function LeadPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>;
  searchParams: SearchParams;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = crmPath(slug, "leads", id);
  const workspace = await workspaceWith(slug, "crm.read", path);
  const record = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/crm/leads/{lead_id}", { params: { path: { slug, lead_id: id } } }),
    ),
    path,
  );
  const canWrite = workspace.permissions.includes("crm.write");

  return (
    <div className="flex flex-col gap-6">
      <RecordHeader
        back={{ href: crmPath(slug, "leads"), label: "Back to leads" }}
        title={record.title}
        badges={
          <>
            <Badge variant={STATUS_VARIANT[record.status]}>{STATUS_LABEL[record.status]}</Badge>
            {record.archived_at ? <Badge variant="secondary">Archived lead</Badge> : null}
          </>
        }
        meta={
          <>
            <span>
              Contact:{" "}
              <Link
                className="text-brand underline-offset-4 hover:underline"
                href={crmPath(slug, "contacts", record.contact.id)}
              >
                {record.contact.full_name}
              </Link>
            </span>
            {record.customer ? (
              <span>
                Customer:{" "}
                <Link
                  className="text-brand underline-offset-4 hover:underline"
                  href={crmPath(slug, "customers", record.customer.id)}
                >
                  {record.customer.name}
                </Link>
              </span>
            ) : null}
            <span>Owner: {record.owner?.display_name ?? "Unassigned"}</span>
            <span>Source: {record.source}</span>
          </>
        }
      />
      {record.lost_reason ? (
        <p className="border-destructive/25 bg-destructive/[0.06] rounded-xl border px-4 py-3 text-sm">
          Reason lost: {record.lost_reason}
        </p>
      ) : null}
      <RecordLayout
        main={
          <>
            {canWrite ? (
              <Panel title="Stage" divided={false}>
                <LeadStatusForm slug={slug} lead={record} />
              </Panel>
            ) : null}
            <Panel title="Lead details" divided={false}>
              {canWrite ? (
                <LeadEditForm slug={slug} lead={record} />
              ) : (
                <p className="text-sm whitespace-pre-wrap">{record.notes || "No notes."}</p>
              )}
              {workspace.permissions.includes("crm.archive") ? (
                <div className="mt-5 border-t pt-4">
                  <ArchiveButton slug={slug} kind="lead" id={id} archived={!!record.archived_at} />
                </div>
              ) : null}
            </Panel>
          </>
        }
        aside={
          <ActivitySection
            slug={slug}
            subjectType="lead"
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
