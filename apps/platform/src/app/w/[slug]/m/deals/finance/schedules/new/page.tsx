import { Panel } from "@onyx/ui/components/page";
import { notFound } from "next/navigation";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

import { contactOptions, param, type SearchParams } from "../../../../crm/data";
import { NewScheduleForm } from "../../../_components/schedule-forms";

export default async function NewSchedulePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = dealsPath(slug, "finance", "schedules", "new");
  const workspace = requireOk(await getWorkspace(slug), path);
  if (!workspace.permissions.includes("finance.manage")) notFound();
  const dealId = param((await searchParams).deal_id, 64);
  let deal: { id: string; title: string } | null = null;
  let defaults = {
    total_cents: null as number | null,
    term_months: null as number | null,
    monthly_cents: null as number | null,
  };
  if (dealId) {
    const found = await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/{deal_id}", { params: { path: { slug, deal_id: dealId } } }),
    );
    if (found.ok) {
      deal = { id: found.data.id, title: found.data.title };
      if (found.data.finance_application_id) {
        const app = await withApi((api) =>
          api.GET("/v1/w/{slug}/deals/finance/applications/{application_id}", {
            params: { path: { slug, application_id: found.data.finance_application_id ?? "" } },
          }),
        );
        if (app.ok && app.data.status === "approved") {
          defaults = {
            total_cents: app.data.estimate?.total_cents ?? null,
            term_months: app.data.term_months ?? null,
            monthly_cents: app.data.monthly_estimate_cents ?? null,
          };
        }
      }
    }
  }
  const contacts = deal ? [] : await contactOptions(slug);
  return (
    <Panel title="New payment schedule" divided={false}>
      <NewScheduleForm slug={slug} deal={deal} contacts={contacts} defaults={defaults} />
    </Panel>
  );
}
