import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";

import { OrganizationsTable } from "./organizations-table";

export default async function AdminOrganizationsPage() {
  const orgs = requireOk(await withApi((api) => api.GET("/v1/admin/organizations")), "/admin");
  return (
    <>
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Organisations</h1>
        <p className="text-muted-foreground text-sm">
          Account metadata only. Viewing tenant business data needs an audited support-access mode,
          which is not built yet.
        </p>
      </div>
      <OrganizationsTable organizations={orgs} />
    </>
  );
}
