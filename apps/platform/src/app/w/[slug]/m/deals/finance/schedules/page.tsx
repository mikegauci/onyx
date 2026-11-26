import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Panel } from "@onyx/ui/components/page";
import { EmptyState } from "@onyx/ui/components/states";
import { Plus } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { euros } from "@/lib/automotive";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";
import { formatDay } from "@/lib/reminders";
import { SCHEDULE_STATUS_LABEL, type ScheduleStatus } from "@/lib/schedules";

import { param, type SearchParams } from "../../../crm/data";

const FILTERS = ["active", "overdue", "completed", "cancelled"] as const;
type Filter = (typeof FILTERS)[number];
const FILTER_LABEL: Record<Filter, string> = {
  active: "Active",
  overdue: "Overdue",
  completed: "Paid in full",
  cancelled: "Cancelled",
};

export default async function SchedulesPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = dealsPath(slug, "finance", "schedules");
  const workspace = requireOk(await getWorkspace(slug), path);
  const raw = param((await searchParams).filter, 20);
  const filter: Filter = FILTERS.includes(raw as Filter) ? (raw as Filter) : "active";
  const list = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/finance/schedules", {
        params: {
          path: { slug },
          query:
            filter === "overdue"
              ? { status: "active", overdue: true }
              : { status: filter as ScheduleStatus },
        },
      }),
    ),
    path,
  );
  return (
    <Panel
      title="Payment schedules"
      description="In-house finance: what each customer owes and what they have paid. Onyx does not take payments; staff record them."
      actions={
        workspace.permissions.includes("finance.manage") ? (
          <Button asChild size="sm">
            <Link href={dealsPath(slug, "finance", "schedules", "new")}>
              <Plus aria-hidden />
              New schedule
            </Link>
          </Button>
        ) : null
      }
      flush
    >
      <nav aria-label="Schedule filter" className="flex flex-wrap gap-2 px-5 pt-4 text-sm">
        {FILTERS.map((f) => (
          <Link
            key={f}
            href={`${path}?filter=${f}`}
            aria-current={f === filter ? "page" : undefined}
            className={
              f === filter
                ? "bg-foreground text-background rounded-full px-3 py-1"
                : "hover:bg-foreground/[0.05] rounded-full border px-3 py-1"
            }
          >
            {FILTER_LABEL[f]}
          </Link>
        ))}
      </nav>
      {list.items.length === 0 ? (
        <div className="p-5">
          <EmptyState
            title="No payment schedules here"
            description="Set one up from a financed deal, or with New schedule."
          />
        </div>
      ) : (
        <ul className="mt-3 divide-y border-t" aria-label="Payment schedules">
          {list.items.map((s) => (
            <li key={s.id}>
              <Link
                href={dealsPath(slug, "finance", "schedules", s.id)}
                className="hover:bg-foreground/[0.03] focus-visible:ring-ring flex flex-wrap items-center gap-3 px-5 py-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="font-medium">{s.contact_name}</span>
                <span className="text-muted-foreground">{s.label}</span>
                <span className="tabular-nums">
                  {euros(s.paid_cents)} of {euros(s.total_cents)} paid
                </span>
                {s.overdue_count > 0 ? (
                  <Badge variant="destructive">{euros(s.overdue_cents)} overdue</Badge>
                ) : null}
                <span className="text-muted-foreground ml-auto text-xs">
                  {s.status === "active" && s.next_due_on
                    ? `Next ${formatDay(s.next_due_on)}`
                    : SCHEDULE_STATUS_LABEL[s.status]}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
