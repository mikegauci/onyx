import { Badge } from "@onyx/ui/components/badge";
import { DetailList, Panel } from "@onyx/ui/components/page";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BackLink } from "@/components/back-link";
import { withApi } from "@/lib/api-client";
import { euros } from "@/lib/automotive";
import { crmPath, formatInZone } from "@/lib/crm";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { APPLICANT_LABEL, MARITAL_LABEL, STATUS_LABEL, STATUS_VARIANT } from "@/lib/finance";
import { requireOk } from "@/lib/guards";

import { EstimateBreakdown, StatusForm } from "../../_components/finance-forms";

type Props = { params: Promise<{ slug: string; id: string }> };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LINK = "text-brand underline-offset-4 hover:underline";

export default async function FinanceApplicationPage({ params }: Props) {
  const { slug, id } = await params;
  if (!UUID.test(id)) notFound();
  const path = dealsPath(slug, "finance", id);
  const workspace = requireOk(await getWorkspace(slug), path);
  const app = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/finance/applications/{application_id}", {
        params: { path: { slug, application_id: id } },
      }),
    ),
    path,
  );
  const canManage = workspace.permissions.includes("finance.manage");
  return (
    <>
      <BackLink href={dealsPath(slug, "finance")}>Back to finance</BackLink>
      <h2 className="flex flex-wrap items-center gap-3 text-2xl font-light tracking-tight">
        Finance · {app.contact.label}
        <Badge variant={STATUS_VARIANT[app.status]}>{STATUS_LABEL[app.status]}</Badge>
      </h2>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <Panel title="Estimate">
            {app.estimate ? (
              <EstimateBreakdown estimate={app.estimate} />
            ) : (
              <p className="text-muted-foreground text-sm">
                Add the price and term to work out the estimate.
              </p>
            )}
          </Panel>
          <Panel
            title="Documents needed"
            description={`For a ${APPLICANT_LABEL[app.applicant_type].toLowerCase()}, ${MARITAL_LABEL[app.marital_status].toLowerCase()}.`}
          >
            <ul className="marker:text-foreground/30 list-disc pl-5 text-sm leading-relaxed">
              {app.checklist.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {app.deal_id ? (
              <p className="text-muted-foreground mt-3 text-sm">
                Collect and check them on the{" "}
                <Link className={LINK} href={dealsPath(slug, app.deal_id)}>
                  deal
                </Link>
                .
              </p>
            ) : null}
          </Panel>
        </div>
        <div className="flex flex-col gap-6">
          <Panel title="Status" as="h3" divided={false}>
            <StatusForm slug={slug} id={id} current={app.status} canManage={canManage} />
          </Panel>
          <Panel title="Details" as="h3" divided={false}>
            <DetailList
              className="sm:grid-cols-1"
              items={[
                {
                  label: "Customer",
                  value: (
                    <Link className={LINK} href={crmPath(slug, "contacts", app.contact.id)}>
                      {app.contact.label}
                    </Link>
                  ),
                },
                { label: "Applicant", value: APPLICANT_LABEL[app.applicant_type] },
                { label: "Marital status", value: MARITAL_LABEL[app.marital_status] },
                ...(app.vehicle_label ? [{ label: "Vehicle", value: app.vehicle_label }] : []),
                ...(app.restricted
                  ? [{ label: "Income", value: "Visible to owners and admins" }]
                  : [
                      { label: "Employer", value: app.employer ?? "—" },
                      {
                        label: "Net monthly income",
                        value:
                          app.net_monthly_income_cents === null
                            ? "—"
                            : euros(app.net_monthly_income_cents),
                      },
                      {
                        label: "Existing commitments",
                        value:
                          app.existing_commitments_cents === null
                            ? "—"
                            : euros(app.existing_commitments_cents),
                      },
                      ...(app.decision_note
                        ? [{ label: "Decision note", value: app.decision_note }]
                        : []),
                    ]),
                ...(app.decided_at
                  ? [{ label: "Decided", value: formatInZone(app.decided_at, workspace.timezone) }]
                  : []),
                {
                  label: "Started",
                  value: `${formatInZone(app.created_at, workspace.timezone)}${app.source === "assistant" ? " (by the assistant)" : ""}`,
                },
              ]}
            />
          </Panel>
        </div>
      </div>
    </>
  );
}
