import Link from "next/link";
import { Badge } from "@onyx/ui/components/badge";
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
      <Link className="text-sm underline" href={crmPath(slug, "leads")}>
        Back to leads
      </Link>
      <h2 className="text-xl font-medium">{record.title}</h2>
      {record.archived_at ? <p className="text-muted-foreground text-sm">Archived lead</p> : null}
      <div className="flex flex-col items-start gap-2">
        <Badge variant={STATUS_VARIANT[record.status]}>{STATUS_LABEL[record.status]}</Badge>
        <p>
          Contact:{" "}
          <Link className="underline" href={crmPath(slug, "contacts", record.contact.id)}>
            {record.contact.full_name}
          </Link>
        </p>
        {record.customer ? (
          <p>
            Customer:{" "}
            <Link className="underline" href={crmPath(slug, "customers", record.customer.id)}>
              {record.customer.name}
            </Link>
          </p>
        ) : null}
        <p>
          Owner: {record.owner?.display_name ?? "Unassigned"} · Source: {record.source}
        </p>
        {record.lost_reason ? <p>Reason lost: {record.lost_reason}</p> : null}
        {canWrite ? <LeadStatusForm slug={slug} lead={record} /> : null}
      </div>
      {canWrite ? (
        <LeadEditForm slug={slug} lead={record} />
      ) : (
        <p className="whitespace-pre-wrap">{record.notes}</p>
      )}

      {workspace.permissions.includes("crm.archive") ? (
        <ArchiveButton slug={slug} kind="lead" id={id} archived={!!record.archived_at} />
      ) : null}
      <ActivitySection
        slug={slug}
        subjectType="lead"
        id={id}
        timezone={workspace.timezone}
        canWrite={canWrite}
        cursor={param((await searchParams).cursor)}
      />
    </div>
  );
}
