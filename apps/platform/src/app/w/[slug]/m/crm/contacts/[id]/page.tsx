import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Panel } from "@onyx/ui/components/page";
import { Building2, Mail, Phone } from "lucide-react";
import Link from "next/link";

import { RecordHeader, RecordLayout } from "@/components/record";
import { withApi } from "@/lib/api-client";
import { crmPath } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { ContactForm, ArchiveButton } from "../../_components/forms";
import { ActivitySection } from "../../_components/activity-section";
import { PrivacyPanel } from "../../_components/privacy-panel";
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
  const archiveForm = workspace.permissions.includes("crm.archive") ? (
    <ArchiveButton slug={slug} kind="contact" id={id} archived={!!record.archived_at} />
  ) : null;
  return (
    <div className="flex flex-col gap-6">
      <RecordHeader
        back={{ href: crmPath(slug, "contacts"), label: "Back to contacts" }}
        title={record.full_name}
        badges={
          record.erased_at ? (
            <Badge variant="outline">Erased</Badge>
          ) : record.archived_at ? (
            <Badge variant="secondary">Archived contact</Badge>
          ) : null
        }
        meta={
          <>
            <span className="inline-flex items-center gap-1.5">
              <Mail aria-hidden className="size-3.5" />
              {record.email ?? "No email"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Phone aria-hidden className="size-3.5" />
              {record.phone ?? "No phone"}
            </span>
            {record.customer ? (
              <Link
                className="text-brand inline-flex items-center gap-1.5 underline-offset-4 hover:underline"
                href={crmPath(slug, "customers", record.customer.id)}
              >
                <Building2 aria-hidden className="size-3.5" />
                {record.customer.name}
              </Link>
            ) : null}
          </>
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <Link href={`${crmPath(slug, "leads")}?contact_id=${id}`}>View related leads</Link>
            </Button>
            {canWrite && !record.archived_at ? (
              <Button asChild size="sm">
                <Link href={`${crmPath(slug, "leads", "new")}?contact_id=${id}`}>
                  New lead for this contact
                </Link>
              </Button>
            ) : null}
          </>
        }
      />
      <RecordLayout
        main={
          <>
            <Panel title="Contact details" divided={false}>
              {canWrite ? (
                <ContactForm slug={slug} contact={record} customers={customers} />
              ) : (
                <p className="text-sm whitespace-pre-wrap">{record.notes || "No notes."}</p>
              )}
              {archiveForm ? <div className="mt-5 border-t pt-4">{archiveForm}</div> : null}
            </Panel>
            {workspace.permissions.includes("privacy.manage") ? (
              <Panel title="Privacy" divided={false}>
                <PrivacyPanel
                  slug={slug}
                  contactId={id}
                  fullName={record.full_name}
                  exportHref={`${path}/export`}
                  erasedAt={record.erased_at ?? null}
                />
              </Panel>
            ) : null}
          </>
        }
        aside={
          <ActivitySection
            slug={slug}
            subjectType="contact"
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
