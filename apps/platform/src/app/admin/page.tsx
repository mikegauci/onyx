import { PageHeader } from "@onyx/ui/components/page";
import { Button } from "@onyx/ui/components/button";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";

import { OrganizationsTable } from "./organizations-table";

export default async function AdminOrganizationsPage() {
  const orgs = requireOk(await withApi((api) => api.GET("/v1/admin/organizations")), "/admin");
  return (
    <>
      <PageHeader
        eyebrow="Platform admin"
        title="Organisations"
        description="Account metadata only. Viewing tenant business data needs an audited support-access mode, which is not built yet."
        actions={
          <Button asChild>
            <Link href="/admin/organizations/new">New organisation</Link>
          </Button>
        }
      />
      <OrganizationsTable organizations={orgs} />
    </>
  );
}
