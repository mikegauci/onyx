import { Button } from "@onyx/ui/components/button";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";

import { OrganizationsTable } from "./organizations-table";

export default async function AdminOrganizationsPage() {
  const orgs = requireOk(await withApi((api) => api.GET("/v1/admin/organizations")), "/admin");
  return (
    <>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
            Organisations
          </h1>
          <Button asChild>
            <Link href="/admin/organizations/new">New organisation</Link>
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">
          Account metadata only. Viewing tenant business data needs an audited support-access mode,
          which is not built yet.
        </p>
      </div>
      <OrganizationsTable organizations={orgs} />
    </>
  );
}
