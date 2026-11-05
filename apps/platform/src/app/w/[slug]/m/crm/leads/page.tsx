import { Button } from "@onyx/ui/components/button";
import Link from "next/link";
import { withApi } from "@/lib/api-client";
import { crmPath, LEAD_STATUSES, STATUS_LABEL } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { ListToolbar, Pager } from "../_components/list-controls";
import { LeadsTable } from "../_components/tables";
import { param, recordId, type SearchParams } from "../data";
import { SELECT_CLASS } from "../../../settings/form-status";
export default async function LeadsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = crmPath(slug, "leads");
  const workspace = await workspaceWith(slug, "crm.read", path);
  const search = await searchParams;
  const q = param(search.q, 100);
  const cursor = param(search.cursor);
  const includeArchived = param(search.include_archived) === "true";
  const contact = param(search.contact_id);
  const customer = param(search.customer_id);
  const contact_id = contact ? recordId(contact) : undefined;
  const customer_id = customer ? recordId(customer) : undefined;
  const statusValue = param(search.status);
  const status = LEAD_STATUSES.find((s) => s === statusValue);
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/crm/leads", {
        params: {
          path: { slug },
          query: { q, cursor, status, contact_id, customer_id, include_archived: includeArchived },
        },
      }),
    ),
    path,
  );
  return (
    <section className="flex flex-col gap-4" aria-labelledby="leads-heading">
      <h2 id="leads-heading" className="text-lg font-medium">
        Leads
      </h2>
      <ListToolbar
        action={path}
        q={q}
        label="Search leads"
        extra={
          <>
            {contact_id ? <input type="hidden" name="contact_id" value={contact_id} /> : null}
            {customer_id ? <input type="hidden" name="customer_id" value={customer_id} /> : null}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="include_archived"
                value="true"
                defaultChecked={includeArchived}
              />
              Include archived
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Status
              <select name="status" defaultValue={status ?? ""} className={SELECT_CLASS}>
                <option value="">All statuses</option>
                {LEAD_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
          </>
        }
      >
        {workspace.permissions.includes("crm.write") ? (
          <Button asChild>
            <Link href={crmPath(slug, "leads", "new")}>New lead</Link>
          </Button>
        ) : null}
      </ListToolbar>
      <LeadsTable slug={slug} leads={page.items} timezone={workspace.timezone} />
      <Pager
        base={path}
        params={{
          q,
          status,
          contact_id,
          customer_id,
          include_archived: includeArchived ? "true" : undefined,
        }}
        cursor={cursor}
        nextCursor={page.next_cursor}
      />
    </section>
  );
}
