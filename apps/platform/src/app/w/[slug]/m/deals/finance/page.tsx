import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Panel } from "@onyx/ui/components/page";
import { EmptyState } from "@onyx/ui/components/states";
import { Plus } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { euros } from "@/lib/automotive";
import { formatInZone } from "@/lib/crm";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { APPLICANT_LABEL, STATUS_LABEL, STATUS_VARIANT } from "@/lib/finance";
import { requireOk } from "@/lib/guards";

import { Calculator } from "../_components/finance-forms";

type Props = { params: Promise<{ slug: string }> };

export default async function FinancePage({ params }: Props) {
  const { slug } = await params;
  const path = dealsPath(slug, "finance");
  const workspace = requireOk(await getWorkspace(slug), path);
  const list = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/finance/applications", { params: { path: { slug } } }),
    ),
    path,
  );
  return (
    <div className="flex flex-col gap-6">
      <Panel title="Finance estimate" description="Work out a monthly payment for a customer.">
        <Calculator slug={slug} />
      </Panel>
      <Panel
        title="Finance applications"
        actions={
          workspace.permissions.includes("deals.write") ? (
            <Button asChild size="sm">
              <Link href={dealsPath(slug, "finance", "new")}>
                <Plus aria-hidden />
                New application
              </Link>
            </Button>
          ) : null
        }
        flush
      >
        {list.items.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title="No finance applications yet"
              description="Start one from a deal, or here when a customer asks about finance."
            />
          </div>
        ) : (
          <ul className="divide-y" aria-label="Finance applications">
            {list.items.map((a) => (
              <li key={a.id}>
                <Link
                  href={dealsPath(slug, "finance", a.id)}
                  className="hover:bg-foreground/[0.03] focus-visible:ring-ring flex flex-wrap items-center gap-3 px-5 py-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  <span className="font-medium">{a.contact.label}</span>
                  <span className="text-muted-foreground">{APPLICANT_LABEL[a.applicant_type]}</span>
                  {a.vehicle_label ? (
                    <span className="text-muted-foreground">{a.vehicle_label}</span>
                  ) : null}
                  {a.monthly_estimate_cents !== null ? (
                    <span className="tabular-nums">{euros(a.monthly_estimate_cents)}/month</span>
                  ) : null}
                  <Badge variant={STATUS_VARIANT[a.status]} className="ml-auto">
                    {STATUS_LABEL[a.status]}
                  </Badge>
                  <time className="text-muted-foreground text-xs" dateTime={a.updated_at}>
                    {formatInZone(a.updated_at, workspace.timezone)}
                  </time>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
