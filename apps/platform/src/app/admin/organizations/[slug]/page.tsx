import { BackLink } from "@/components/back-link";
import { Badge } from "@onyx/ui/components/badge";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { billingStatus } from "@/lib/billing";
import { usdFromMicros } from "@/lib/tenants";

import { IntegrationList } from "../../../w/[slug]/settings/integrations/integration-list";
import { ConnectPhoneLineForm, ConnectWhatsAppForm, DisconnectButton } from "./connect-forms";
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
  const [detailResult, invitationsResult, integrationsResult, billingResult] = await Promise.all([
    withApi((api) => api.GET("/v1/admin/organizations/{slug}", opts)),
    withApi((api) => api.GET("/v1/admin/organizations/{slug}/invitations", opts)),
    withApi((api) => api.GET("/v1/admin/organizations/{slug}/integrations", opts)),
    withApi((api) => api.GET("/v1/admin/organizations/{slug}/billing", opts)),
  ]);
  const detail = requireOk(detailResult, path);
  const invitations = requireOk(invitationsResult, path);
  const integrations = requireOk(integrationsResult, path);
  const billing = requireOk(billingResult, path);
  const billingView = billingStatus(billing.status);
  const org = detail.organization;
  const timezones = Intl.supportedValuesOf("timeZone");
  if (!timezones.includes(org.timezone)) timezones.unshift(org.timezone);
  const budget = integrations.ai_budget;

  return (
    <>
      <BackLink href="/admin">Back to organisations</BackLink>
      <div className="flex flex-col gap-1">
        <h1 className="flex flex-wrap items-center gap-3 text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
          {org.name}
          <Badge variant={org.status === "suspended" ? "destructive" : "success"}>
            {org.status === "suspended" ? "Suspended" : "Active"}
          </Badge>
        </h1>
        <p className="text-muted-foreground text-sm">
          <code>{org.slug}</code> · {org.member_count} members · {org.timezone} · {org.currency}
        </p>
      </div>

      <section
        aria-labelledby="details-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="details-heading" className="text-base font-medium tracking-tight">
          Details
        </h2>
        <DetailsForm org={org} timezones={timezones} />
      </section>

      <section
        aria-labelledby="status-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="status-heading" className="text-base font-medium tracking-tight">
          Status
        </h2>
        {/* Remounted when the status changes, so the button always acts on the current one. */}
        <StatusControl key={org.status} slug={org.slug} name={org.name} status={org.status} />
      </section>

      <section
        aria-labelledby="invitations-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="invitations-heading" className="text-base font-medium tracking-tight">
          Invitations
        </h2>
        <p className="text-muted-foreground text-sm">
          Links are shown once, when created. A new link to the same address replaces the old one.
        </p>
        {invitations.length === 0 ? (
          <p className="text-muted-foreground text-sm">No invitations.</p>
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

      <section
        aria-labelledby="billing-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="billing-heading" className="text-base font-medium tracking-tight">
          Billing
        </h2>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium capitalize">{billing.plan ?? "No plan"}</span>
          <Badge variant={billingView.variant}>{billingView.label}</Badge>
          {billing.current_period_end ? (
            <span className="text-muted-foreground">
              {billing.cancel_at_period_end ? "Ends" : "Renews"}{" "}
              {formatInZone(billing.current_period_end, org.timezone)}
            </span>
          ) : null}
          {!billing.has_customer ? (
            <span className="text-muted-foreground">No Stripe customer yet</span>
          ) : null}
        </p>
        <p className="text-muted-foreground text-xs">
          Read-only: plans change through Stripe (the owner&apos;s checkout or billing portal). The
          plan decides the modules below at each change.
        </p>
      </section>

      <section
        aria-labelledby="budget-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="budget-heading" className="text-base font-medium tracking-tight">
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

      <section
        aria-labelledby="integrations-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="integrations-heading" className="text-base font-medium tracking-tight">
          Integrations
        </h2>
        <IntegrationList status={integrations} />
      </section>

      {integrations.channels.some((c) => c.kind === "whatsapp" && c.phone_number) ||
      (integrations.phone_lines ?? []).length > 0 ? (
        <section
          aria-labelledby="connected-numbers-heading"
          className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
        >
          <h2 id="connected-numbers-heading" className="text-base font-medium tracking-tight">
            Connected numbers
          </h2>
          <p className="text-muted-foreground text-sm">
            To replace a WhatsApp number, disconnect it, then connect the new one with the same
            channel name. Conversations and history stay.
          </p>
          <ul className="flex flex-col gap-3" aria-label="Connected numbers">
            {integrations.channels
              .filter((c) => c.kind === "whatsapp" && c.phone_number)
              .map((c) => (
                <li key={c.id} className="flex flex-col gap-2 rounded-xl border p-3 text-sm">
                  <span>
                    <span className="font-medium">{c.phone_number}</span>{" "}
                    <span className="text-muted-foreground">WhatsApp · {c.name}</span>
                  </span>
                  <DisconnectButton
                    slug={org.slug}
                    kind="whatsapp"
                    id={c.id}
                    label={c.phone_number ?? c.name}
                  />
                </li>
              ))}
            {(integrations.phone_lines ?? []).map((line) => (
              <li key={line.id} className="flex flex-col gap-2 rounded-xl border p-3 text-sm">
                <span>
                  <span className="font-medium">{line.number}</span>{" "}
                  <span className="text-muted-foreground">
                    Missed calls → {line.whatsapp_channel_name}
                  </span>
                </span>
                <DisconnectButton slug={org.slug} kind="line" id={line.id} label={line.number} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section
        aria-labelledby="connect-whatsapp-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="connect-whatsapp-heading" className="text-base font-medium tracking-tight">
          Connect a WhatsApp number
        </h2>
        <ConnectWhatsAppForm slug={org.slug} configured={integrations.whatsapp_configured} />
      </section>

      <section
        aria-labelledby="connect-line-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="connect-line-heading" className="text-base font-medium tracking-tight">
          Connect a phone line (missed-call text-back)
        </h2>
        <ConnectPhoneLineForm
          slug={org.slug}
          configured={integrations.telephony_configured ?? false}
          whatsappChannels={integrations.channels
            .filter((c) => c.kind === "whatsapp" && c.connected)
            .map((c) => c.name)}
        />
      </section>

      <section
        aria-labelledby="entitlements-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="entitlements-heading" className="text-base font-medium tracking-tight">
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
