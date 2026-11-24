import { BackLink } from "@/components/back-link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";

import { NewOrganizationForm } from "./new-organization-form";

export default async function NewOrganizationPage() {
  const path = "/admin/organizations/new";
  const modules = requireOk(await withApi((api) => api.GET("/v1/admin/modules")), path);
  const timezones = Intl.supportedValuesOf("timeZone");
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <BackLink href="/admin">Back to organisations</BackLink>
      <div className="flex flex-col gap-1">
        <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
          New organisation
        </h1>
        <p className="text-muted-foreground text-sm">
          Creates the workspace, turns on its modules and invites its first owner. Everything is
          recorded in the new workspace&apos;s audit log as Onyx staff.
        </p>
      </div>
      <NewOrganizationForm modules={modules} timezones={timezones} />
    </div>
  );
}
