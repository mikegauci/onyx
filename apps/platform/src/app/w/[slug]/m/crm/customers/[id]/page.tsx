import Link from "next/link";

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
      <Link className="text-sm underline" href={crmPath(slug, "customers")}>
        Back to customers
      </Link>
      <h2 className="text-xl font-medium">{record.name}</h2>
      {record.archived_at ? (
        <p className="text-muted-foreground text-sm">Archived customer</p>
      ) : null}
      <div className="flex flex-col items-start gap-2">
        <p>
          {record.kind === "business" ? "Business" : "Individual"} ·{" "}
          {record.vat_number ?? "No VAT number"}
        </p>
      </div>
      {canWrite ? (
        <CustomerForm slug={slug} customer={record} />
      ) : (
        <p className="whitespace-pre-wrap">{record.notes}</p>
      )}
      {workspace.permissions.includes("crm.archive") ? (
        <ArchiveButton slug={slug} kind="customer" id={id} archived={!!record.archived_at} />
      ) : null}
      <Link className="text-sm underline" href={`${crmPath(slug, "leads")}?customer_id=${id}`}>
        View related leads
      </Link>
      <ActivitySection
        slug={slug}
        subjectType="customer"
        id={id}
        timezone={workspace.timezone}
        canWrite={canWrite}
        cursor={param((await searchParams).cursor)}
      />
    </div>
  );
}
