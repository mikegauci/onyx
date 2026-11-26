import { Badge } from "@onyx/ui/components/badge";
import { Panel } from "@onyx/ui/components/page";
import Link from "next/link";

import { RecordHeader } from "@/components/record";
import { withApi } from "@/lib/api-client";
import { euros } from "@/lib/automotive";
import { crmPath } from "@/lib/crm";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";
import { formatDay } from "@/lib/reminders";
import { paidPercent, SCHEDULE_STATUS_LABEL } from "@/lib/schedules";

import { recordId } from "../../../../crm/data";
import {
  InstallmentTable,
  PaymentForm,
  PaymentList,
  ScheduleSettingsForm,
} from "../../../_components/schedule-forms";

export default async function SchedulePage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = dealsPath(slug, "finance", "schedules", id);
  const workspace = requireOk(await getWorkspace(slug), path);
  const schedule = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/finance/schedules/{schedule_id}", {
        params: { path: { slug, schedule_id: id } },
      }),
    ),
    path,
  );
  const canManage = workspace.permissions.includes("finance.manage");
  const percent = paidPercent(schedule);
  return (
    <div className="flex flex-col gap-6">
      <RecordHeader
        back={{ href: dealsPath(slug, "finance", "schedules"), label: "Back to schedules" }}
        title={`${schedule.contact_name} · ${schedule.label}`}
        badges={
          <>
            <Badge variant={schedule.status === "active" ? "secondary" : "outline"}>
              {SCHEDULE_STATUS_LABEL[schedule.status]}
            </Badge>
            {schedule.overdue_count > 0 ? (
              <Badge variant="destructive">{euros(schedule.overdue_cents)} overdue</Badge>
            ) : null}
            {schedule.reminders_paused ? <Badge variant="outline">Reminders paused</Badge> : null}
          </>
        }
        meta={
          <>
            <Link
              className="underline-offset-4 hover:underline"
              href={crmPath(slug, "contacts", schedule.contact_id)}
            >
              Customer
            </Link>
            {schedule.deal_id ? (
              <Link
                className="underline-offset-4 hover:underline"
                href={dealsPath(slug, schedule.deal_id)}
              >
                Deal
              </Link>
            ) : null}
            <span>
              {schedule.term_months} months · {euros(schedule.monthly_cents)}/month
            </span>
          </>
        }
      />
      <Panel title="Balance" divided={false}>
        <div className="flex flex-col gap-3 text-sm">
          <p className="tabular-nums">
            <strong>{euros(schedule.paid_cents)}</strong> paid of {euros(schedule.total_cents)} ·{" "}
            {euros(schedule.outstanding_cents)} outstanding
          </p>
          <div
            className="bg-muted h-2 w-full max-w-md overflow-hidden rounded-full"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Share paid"
          >
            <div className="bg-foreground h-full" style={{ width: `${percent}%` }} />
          </div>
          {schedule.next_due_on ? (
            <p className="text-muted-foreground">
              Next: {euros(schedule.next_due_cents)} due {formatDay(schedule.next_due_on)}
            </p>
          ) : null}
        </div>
      </Panel>
      {canManage && schedule.status !== "cancelled" ? (
        <Panel title="Record a payment" divided={false}>
          <PaymentForm slug={slug} scheduleId={schedule.id} />
        </Panel>
      ) : null}
      <Panel title="Installments" flush>
        <InstallmentTable slug={slug} schedule={schedule} canManage={canManage} />
      </Panel>
      <Panel title="Payments" flush>
        <PaymentList slug={slug} schedule={schedule} canManage={canManage} />
      </Panel>
      {canManage ? (
        <Panel title="Schedule" divided={false}>
          <ScheduleSettingsForm slug={slug} schedule={schedule} />
        </Panel>
      ) : null}
    </div>
  );
}
