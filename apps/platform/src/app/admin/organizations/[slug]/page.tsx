import { Badge } from "@onyx/ui/components/badge";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { usdFromMicros } from "@/lib/tenants";

import { IntegrationList } from "../../../w/[slug]/settings/integrations/integration-list";
import { ModuleToggles } from "./module-toggles";
import {
  BudgetForm,
  DetailsForm,
  InvitationRow,
  NewInvitationForm,
  StatusControl,
} from "./org-forms";

type Props = { params: Promise<{ slug: string }> };

export default async function AdminOrganizationPage({ params }: Props) {
  const { slug } = await params;
  const path = `/admin/organizations/${slug}`;
  const opts = { params: { path: { slug } } };
  const [detailResult, invitationsResult, integrationsResult] = await Promise.all([
    withApi((api) => api.GET("/v1/admin/organizations/{slug}", opts)),
    withApi((api) => api.GET("/v1/admin/organizations/{slug}/invitations", opts)),
    withApi((api) => api.GET("/v1/admin/organizations/{slug}/integrations", opts)),
  ]);
  const detail = requireOk(detailResult, path);
  const invitations = requireOk(invitationsResult, path);
  const integrations = requireOk(integrationsResult, path);
  const org = detail.organization;
  const timezones = Intl.supportedValuesOf("timeZone");
  if (!timezones.includes(org.timezone)) timezones.unshift(org.timezone);
  const budget = integrations.ai_budget;

  return (
    <>
      <Link className="text-sm underline" href="/admin">
        Back to organisations
      </Link>
      <div className="flex flex-col gap-1">
        <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
          {org.name}
          <Badge variant={org.status === "suspended" ? "destructive" : "success"}>
            {org.status === "suspended" ? "Suspended" : "Active"}
          </Badge>
        </h1>
        <p className="text-muted-foreground text-sm">
          <code>{org.slug}</code> · {org.member_count} members · {org.timezone} · {org.currency}
        </p>
      </div>

      <section aria-labelledby="details-heading" className="flex flex-col gap-3">
        <h2 id="details-heading" className="text-lg font-medium">
          Details
        </h2>
        <DetailsForm org={org} timezones={timezones} />
      </section>

      <section aria-labelledby="status-heading" className="flex flex-col gap-3">
        <h2 id="status-heading" className="text-lg font-medium">
          Status
        </h2>
        {/* Remounted when the status changes, so the button always acts on the current one. */}
        <StatusControl key={org.status} slug={org.slug} name={org.name} status={org.status} />
      </section>

      <section aria-labelledby="invitations-heading" className="flex flex-col gap-3">
        <h2 id="invitations-heading" className="text-lg font-medium">
          Invitations
        </h2>
        <p className="text-muted-foreground text-sm">
          Links are shown once, when created. A new link to the same address replaces the old one.
        </p>
        {invitations.length === 0 ? (
          <p className="text-sm">No invitations.</p>
        ) : (
          <ul className="flex flex-col gap-2" aria-label="Invitations">
            {invitations.map((invitation) => (
              <InvitationRow
                key={invitation.id}
                slug={org.slug}
                invitation={invitation}
                created={formatInZone(invitation.created_at, org.timezone)}
              />
            ))}
          </ul>
        )}
        <NewInvitationForm slug={org.slug} />
      </section>

      <section aria-labelledby="budget-heading" className="flex flex-col gap-3">
        <h2 id="budget-heading" className="text-lg font-medium">
          AI budget
        </h2>
        <p className="text-sm">
          Spent this month: {usdFromMicros(budget?.spent_usd_micros ?? 0)} of{" "}
          {usdFromMicros(budget?.monthly_limit_usd_micros)}
        </p>
        <BudgetForm
          slug={org.slug}
          limitMicros={budget?.monthly_limit_usd_micros ?? null}
          alertPercent={budget?.alert_percent ?? null}
        />
      </section>

      <section aria-labelledby="integrations-heading" className="flex flex-col gap-3">
        <h2 id="integrations-heading" className="text-lg font-medium">
          Integrations
        </h2>
        <IntegrationList status={integrations} />
      </section>

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
