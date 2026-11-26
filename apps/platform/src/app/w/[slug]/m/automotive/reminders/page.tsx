import { EmptyState } from "@onyx/ui/components/states";
import { BellRing } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { requireOk } from "@/lib/guards";
import {
  REMINDER_KIND_LABEL,
  REMINDER_KINDS,
  REMINDER_STATUS_LABEL,
  REMINDER_STATUSES,
  type ReminderKind,
  type ReminderStatus,
} from "@/lib/reminders";
import { workspaceWith } from "@/lib/settings-guard";

import { param, type SearchParams } from "../../crm/data";
import { ReminderList } from "../_components/reminders";

export default async function RemindersPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = automotivePath(slug, "reminders");
  const workspace = await workspaceWith(slug, "crm.read", path);
  const query = await searchParams;
  const rawStatus = param(query.status, 20);
  const status = REMINDER_STATUSES.includes(rawStatus as ReminderStatus)
    ? (rawStatus as ReminderStatus)
    : "pending";
  const rawKind = param(query.kind, 20);
  const kind = REMINDER_KINDS.includes(rawKind as ReminderKind) ? (rawKind as ReminderKind) : null;
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/reminders", {
        params: { path: { slug }, query: { status, kind, limit: 100 } },
      }),
    ),
    path,
  );
  const href = (s: ReminderStatus, k: ReminderKind | null) =>
    `${path}?status=${s}${k ? `&kind=${k}` : ""}`;
  const pill = (active: boolean) =>
    active
      ? "bg-foreground text-background rounded-full px-3 py-1"
      : "hover:bg-foreground/[0.05] rounded-full border px-3 py-1";
  return (
    <section className="flex flex-col gap-4" aria-labelledby="reminders-heading">
      <h2 id="reminders-heading" className="sr-only">
        Reminders
      </h2>
      <nav aria-label="Reminder status" className="flex flex-wrap gap-2 text-sm">
        {REMINDER_STATUSES.map((s) => (
          <Link
            key={s}
            href={href(s, kind)}
            aria-current={s === status ? "page" : undefined}
            className={pill(s === status)}
          >
            {REMINDER_STATUS_LABEL[s]}
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
        {REMINDER_KINDS.map((k) => (
          <Link
            key={k}
            href={href(status, k)}
            aria-current={k === kind ? "page" : undefined}
            className={pill(k === kind)}
          >
            {REMINDER_KIND_LABEL[k]}
          </Link>
        ))}
      </nav>
      <p className="text-muted-foreground max-w-prose text-sm">
        Road licence and insurance reminders appear for cars where you handle them for the customer;
        service reminders follow each car’s service interval. Sending uses WhatsApp when the
        customer has written to you (the template after 24 hours), otherwise email. Add and edit
        cars on each contact’s page.
      </p>
      {page.items.length === 0 ? (
        <EmptyState
          icon={BellRing}
          title="No reminders"
          description="They appear here as each car’s due dates come up."
        />
      ) : (
        <ReminderList
          slug={slug}
          items={page.items}
          canSend={workspace.permissions.includes("outbound.approve")}
          canWrite={workspace.permissions.includes("crm.write")}
        />
      )}
    </section>
  );
}
