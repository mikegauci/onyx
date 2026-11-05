import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { crmPath } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { ContactForm, ArchiveButton } from "../../_components/forms";
import { ActivitySection } from "../../_components/activity-section";
import { recordId, param, type SearchParams, customerOptions } from "../../data";
export default async function ContactPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>;
  searchParams: SearchParams;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = crmPath(slug, "contacts", id);
  const workspace = await workspaceWith(slug, "crm.read", path);
  const record = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/crm/contacts/{contact_id}", {
        params: { path: { slug, contact_id: id } },
      }),
    ),
    path,
  );
  const canWrite = workspace.permissions.includes("crm.write");
  const customers = canWrite ? await customerOptions(slug) : [];
  if (record.customer && !customers.some((c) => c.id === record.customer?.id))
    customers.unshift({ id: record.customer.id, label: record.customer.name });
  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm underline" href={crmPath(slug, "contacts")}>
        Back to contacts
      </Link>
      <h2 className="text-xl font-medium">{record.full_name}</h2>
      {record.archived_at ? (
        <p className="text-muted-foreground text-sm">Archived contact</p>
      ) : null}
      <div className="flex flex-col items-start gap-2">
        <p>
          {record.email ?? "No email"} · {record.phone ?? "No phone"}
        </p>
        {record.customer ? (
          <Link className="underline" href={crmPath(slug, "customers", record.customer.id)}>
            {record.customer.name}
          </Link>
        ) : null}
      </div>
      {canWrite ? (
        <ContactForm slug={slug} contact={record} customers={customers} />
      ) : (
        <p className="whitespace-pre-wrap">{record.notes}</p>
      )}
      {workspace.permissions.includes("crm.archive") ? (
        <ArchiveButton slug={slug} kind="contact" id={id} archived={!!record.archived_at} />
      ) : null}
      <Link className="text-sm underline" href={`${crmPath(slug, "leads")}?contact_id=${id}`}>
        View related leads
      </Link>
      {canWrite && !record.archived_at ? (
        <Link
          className="text-sm underline"
          href={`${crmPath(slug, "leads", "new")}?contact_id=${id}`}
        >
          New lead for this contact
        </Link>
      ) : null}
      <ActivitySection
        slug={slug}
        subjectType="contact"
        id={id}
        timezone={workspace.timezone}
        canWrite={canWrite}
        cursor={param((await searchParams).cursor)}
      />
    </div>
  );
}
