import { EmptyState } from "@onyx/ui/components/states";
import { BellRing } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";
import {
  PAYMENT_REMINDER_KINDS,
  PAYMENT_REMINDER_LABEL,
  type PaymentReminderKind,
} from "@/lib/schedules";

import { param, type SearchParams } from "../../../crm/data";
import { PaymentReminderList } from "../../_components/payment-reminders";

const STATUSES = ["pending", "skipped", "sent", "dismissed"] as const;
type Status = (typeof STATUSES)[number];
const STATUS_LABEL: Record<Status, string> = {
  pending: "To send",
  skipped: "Not sent",
  sent: "Sent",
  dismissed: "Dismissed",
};

export default async function PaymentRemindersPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = dealsPath(slug, "finance", "reminders");
  const workspace = requireOk(await getWorkspace(slug), path);
  const query = await searchParams;
  const rawStatus = param(query.status, 20);
  const status: Status = STATUSES.includes(rawStatus as Status) ? (rawStatus as Status) : "pending";
  const rawKind = param(query.kind, 20);
  const kind = PAYMENT_REMINDER_KINDS.includes(rawKind as PaymentReminderKind)
    ? (rawKind as PaymentReminderKind)
    : null;
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/finance/reminders", {
        params: { path: { slug }, query: { status, kind, limit: 100 } },
      }),
    ),
    path,
  );
  const href = (s: Status, k: PaymentReminderKind | null) =>
    `${path}?status=${s}${k ? `&kind=${k}` : ""}`;
  const pill = (active: boolean) =>
    active
      ? "bg-foreground text-background rounded-full px-3 py-1"
      : "hover:bg-foreground/[0.05] rounded-full border px-3 py-1";
  return (
    <section className="flex flex-col gap-4" aria-labelledby="payment-reminders-heading">
      <h2 id="payment-reminders-heading" className="sr-only">
        Payment reminders
      </h2>
      <nav aria-label="Reminder status" className="flex flex-wrap gap-2 text-sm">
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={href(s, kind)}
            aria-current={s === status ? "page" : undefined}
            className={pill(s === status)}
          >
            {STATUS_LABEL[s]}
          </Link>
        ))}
        <span className="text-muted-foreground ml-auto self-center font-mono text-[11px] tracking-[0.15em] uppercase">
          {page.total} reminders
        </span>
      </nav>
      <nav aria-label="Reminder kind" className="flex flex-wrap gap-2 text-sm">
        <Link href={href(status, null)} className={pill(kind === null)}>
          All
        </Link>
        {PAYMENT_REMINDER_KINDS.map((k) => (
          <Link
            key={k}
            href={href(status, k)}
            aria-current={k === kind ? "page" : undefined}
            className={pill(k === kind)}
          >
            {PAYMENT_REMINDER_LABEL[k]}
          </Link>
        ))}
      </nav>
      <p className="text-muted-foreground max-w-prose text-sm">
        Unpaid installments appear here a few days before they are due and again if they are
        overdue. Sending uses WhatsApp when the customer has written to you (the template after 24
        hours), otherwise email. Paused schedules get no reminders; set the wording in Settings.
      </p>
      {page.items.length === 0 ? (
        <EmptyState
          icon={BellRing}
          title="No payment reminders"
          description="They appear here as installments come due."
        />
      ) : (
        <PaymentReminderList
          slug={slug}
          items={page.items}
          canSend={workspace.permissions.includes("outbound.approve")}
          canWrite={workspace.permissions.includes("deals.write")}
        />
      )}
    </section>
  );
}
