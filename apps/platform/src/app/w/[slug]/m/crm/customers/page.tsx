import { Button } from "@onyx/ui/components/button";
import Link from "next/link";
import { withApi } from "@/lib/api-client";
import { crmPath } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { ListToolbar, Pager } from "../_components/list-controls";
import { CustomersTable } from "../_components/tables";
import { param, type SearchParams } from "../data";

export default async function CustomersPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = crmPath(slug, "customers");
  const workspace = await workspaceWith(slug, "crm.read", path);
  const search = await searchParams;
  const q = param(search.q, 100);
  const cursor = param(search.cursor);
  const includeArchived = param(search.include_archived) === "true";
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/crm/customers", {
        params: { path: { slug }, query: { q, cursor, include_archived: includeArchived } },
      }),
    ),
    path,
  );
  return (
    <section className="flex flex-col gap-4" aria-labelledby="customers-heading">
      <h2 id="customers-heading" className="text-lg font-medium">
        Customers
      </h2>
      <ListToolbar
        action={path}
        q={q}
        label="Search customers"
        extra={
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="include_archived"
              value="true"
              defaultChecked={includeArchived}
            />
            Include archived
          </label>
        }
      >
        {workspace.permissions.includes("crm.write") ? (
          <Button asChild>
            <Link href={crmPath(slug, "customers", "new")}>New customer</Link>
          </Button>
        ) : null}
      </ListToolbar>
      <CustomersTable slug={slug} customers={page.items} />
      <Pager
        base={path}
        params={{ q, include_archived: includeArchived ? "true" : undefined }}
        cursor={cursor}
        nextCursor={page.next_cursor}
      />
    </section>
  );
}
