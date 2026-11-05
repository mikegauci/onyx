import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";

import { ModuleToggles } from "./module-toggles";

type Props = { params: Promise<{ slug: string }> };

export default async function AdminOrganizationPage({ params }: Props) {
  const { slug } = await params;
  const path = `/admin/organizations/${slug}`;
  const detail = requireOk(
    await withApi((api) =>
      api.GET("/v1/admin/organizations/{slug}", { params: { path: { slug } } }),
    ),
    path,
  );
  const org = detail.organization;
  return (
    <>
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{org.name}</h1>
        <p className="text-muted-foreground text-sm">
          <code>{org.slug}</code> · {org.status} · {org.member_count} members · {org.timezone}
        </p>
      </div>
      <section aria-labelledby="entitlements-heading" className="flex flex-col gap-3">
        <h2 id="entitlements-heading" className="text-lg font-medium">
          Module entitlements
        </h2>
        <p className="text-muted-foreground text-sm">
          Changes take effect immediately for this organisation only and are recorded in its audit
          log as Onyx staff.
        </p>
        <ModuleToggles slug={org.slug} modules={detail.modules} />
      </section>
    </>
  );
}
