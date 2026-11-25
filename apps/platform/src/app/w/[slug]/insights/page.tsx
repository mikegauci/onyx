import { PageHeader, Panel } from "@onyx/ui/components/page";
import { cn } from "@onyx/ui/lib/utils";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import {
  baselineNote,
  CHANNEL_LABEL,
  formatDuration,
  type Insights,
  label,
  parseRange,
  percent,
  RANGES,
  RUN_REASON_LABEL,
  SKIP_REASON_LABEL,
} from "@/lib/insights";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const FOCUS = "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none";

export default async function InsightsPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const days = parseRange((await searchParams).days);
  const path = `/w/${slug}/insights`;
  const workspace = requireOk(await getWorkspace(slug), path);
  const data = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/insights", { params: { path: { slug }, query: { days } } }),
    ),
    path,
  );

  return (
    <>
      <PageHeader
        eyebrow="Pilot"
        title="Insights"
        description={`How ${workspace.display_name ?? workspace.name} is handling enquiries over the last ${days} days. Worked out from the inbox, replies and quotes; no message text is used.`}
        actions={<RangePicker base={path} days={days} />}
      />
      <Headline data={data} />
      <div className="grid gap-6 lg:grid-cols-2">
        {data.enquiries ? (
          <Panel title="Enquiries by channel" description="New conversations in the period.">
            <Bars
              total={data.enquiries.total}
              empty="No new conversations yet."
              rows={data.enquiries.by_channel.map((c) => ({
                label: label(CHANNEL_LABEL, c.key),
                value: c.count,
              }))}
            />
          </Panel>
        ) : null}
        {data.response_time ? (
          <Panel
            title="Response time"
            description="From the customer’s first message to the first reply by a person. Automatic messages are not counted."
          >
            <Facts
              items={[
                ["Median", formatDuration(data.response_time.median_seconds)],
                ["Slowest 10% (over)", formatDuration(data.response_time.p90_seconds)],
                ["Answered", String(data.response_time.answered)],
                ["Still waiting for a reply", String(data.response_time.unanswered)],
                ["Automatic messages sent", String(data.response_time.automatic_replies)],
              ]}
            />
          </Panel>
        ) : null}
        {data.drafts ? (
          <Panel
            title="Assistant replies"
            description="What happened to the replies the assistant drafted."
          >
            <Bars
              total={data.drafts.total}
              empty="The assistant has not drafted any replies yet."
              rows={[
                { label: "Sent as written", value: data.drafts.sent_as_written },
                { label: "Sent after an edit", value: data.drafts.sent_after_edit },
                { label: "Rejected", value: data.drafts.rejected },
                { label: "Expired", value: data.drafts.expired },
                { label: "Replaced by a newer draft", value: data.drafts.superseded },
                { label: "Waiting", value: data.drafts.waiting },
              ]}
            />
            <p className="text-muted-foreground mt-4 text-sm">
              Median wait for approval:{" "}
              <span className="text-foreground font-medium">
                {formatDuration(data.drafts.median_approval_seconds)}
              </span>
            </p>
          </Panel>
        ) : null}
        {data.runs ? (
          <Panel
            title="Hand-offs to staff"
            description="Runs where the assistant passed the conversation to a person, and why."
          >
            <Facts
              items={[
                ["Assistant runs", String(data.runs.total)],
                ["Drafted a reply and quote", String(data.runs.drafted)],
                ["Handed to staff", String(data.runs.escalated)],
              ]}
            />
            {data.runs.top_reasons.length > 0 ? (
              <div className="mt-4">
                <Bars
                  total={data.runs.escalated}
                  empty=""
                  heading="Most common reasons"
                  rows={data.runs.top_reasons.map((r) => ({
                    label: label(RUN_REASON_LABEL, r.key),
                    value: r.count,
                  }))}
                />
              </div>
            ) : null}
          </Panel>
        ) : null}
        {data.quotes ? (
          <Panel
            title="Quotes"
            description="Quotes created in the period, and how far they got. The pilot goal is one enquiry all the way to a sent, approved quote."
          >
            <Funnel
              steps={[
                ["Created", data.quotes.created],
                ["Approved", data.quotes.approved],
                ["Sent to the customer", data.quotes.sent],
                ["Accepted", data.quotes.accepted],
              ]}
            />
          </Panel>
        ) : null}
        {data.deals ? (
          <Panel
            title="Deals"
            description="Sales from reservation to collection, and documents customers sent with their link."
          >
            <Facts
              items={[
                ["New deals", String(data.deals.created)],
                ["Marked sold", String(data.deals.sold)],
                ["Collected", String(data.deals.collected)],
                ["Cancelled", String(data.deals.cancelled)],
                ["Open right now", String(data.deals.open_now)],
                ["Documents uploaded by customers", String(data.deals.customer_uploads)],
              ]}
            />
          </Panel>
        ) : null}
        {data.finance && (data.finance.started > 0 || data.finance.open_now > 0) ? (
          <Panel
            title="Finance"
            description="Finance applications started in the period, and decisions recorded."
          >
            <Facts
              items={[
                ["Applications started", String(data.finance.started)],
                ["Started by the assistant", String(data.finance.by_assistant)],
                ["Approved", String(data.finance.approved)],
                ["Declined", String(data.finance.declined)],
                ["Open right now", String(data.finance.open_now)],
              ]}
            />
          </Panel>
        ) : null}
        {data.missed_calls && data.missed_calls.total > 0 ? (
          <Panel title="Missed calls" description="Calls forwarded to Onyx when nobody answered.">
            <Facts
              items={[
                ["Missed calls", String(data.missed_calls.total)],
                ["WhatsApp text-back sent", String(data.missed_calls.whatsapp_sent)],
                ["SMS text-back sent", String(data.missed_calls.sms_sent)],
                ["No text-back", String(data.missed_calls.skipped + data.missed_calls.failed)],
              ]}
            />
            {data.missed_calls.skip_reasons.length > 0 ? (
              <div className="mt-4">
                <Bars
                  total={data.missed_calls.skipped}
                  empty=""
                  heading="Why no text-back"
                  rows={data.missed_calls.skip_reasons.map((r) => ({
                    label: label(SKIP_REASON_LABEL, r.key),
                    value: r.count,
                  }))}
                />
              </div>
            ) : null}
          </Panel>
        ) : null}
      </div>
    </>
  );
}

function RangePicker({ base, days }: { base: string; days: number }) {
  return (
    <nav aria-label="Period" className="bg-foreground/[0.05] flex gap-1 rounded-full border p-1">
      {RANGES.map((n) => (
        <Link
          key={n}
          href={`${base}?days=${n}`}
          aria-current={n === days ? "page" : undefined}
          className={cn(
            FOCUS,
            "rounded-full px-3.5 py-1.5 text-sm transition-colors",
            n === days
              ? "bg-foreground/10 text-foreground font-medium"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {n} days
        </Link>
      ))}
    </nav>
  );
}

function Headline({ data }: { data: Insights }) {
  const sentDrafts = data.drafts ? data.drafts.sent_as_written + data.drafts.sent_after_edit : 0;
  const tiles: { label: string; value: string; note?: string | null }[] = [];
  if (data.enquiries) {
    const perWeek = Math.round((data.enquiries.total / data.days) * 7);
    tiles.push({
      label: "Enquiries",
      value: String(data.enquiries.total),
      note: data.baseline.enquiries_per_week
        ? `${perWeek} a week · before Onyx: ${data.baseline.enquiries_per_week} a week`
        : `${perWeek} a week`,
    });
  }
  if (data.response_time) {
    tiles.push({
      label: "Median first reply",
      value: formatDuration(data.response_time.median_seconds),
      note: baselineNote(data.baseline.first_reply_minutes),
    });
  }
  if (data.drafts) {
    const share = percent(data.drafts.sent_as_written, sentDrafts);
    tiles.push({
      label: "Assistant drafts sent unedited",
      value: share === null ? "—" : `${share}%`,
      note: `${sentDrafts} sent of ${data.drafts.total} drafted`,
    });
  }
  if (data.quotes) {
    tiles.push({
      label: "Quotes sent",
      value: String(data.quotes.sent),
      note: `${data.quotes.accepted} accepted`,
    });
  }
  if (tiles.length === 0) return null;
  return (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="bg-card flex flex-col gap-1.5 rounded-2xl border p-5">
          <dt className="text-muted-foreground font-mono text-[11px] tracking-[0.12em] uppercase">
            {t.label}
          </dt>
          <dd className="text-3xl font-semibold tracking-tight tabular-nums">{t.value}</dd>
          {t.note ? <dd className="text-muted-foreground text-xs">{t.note}</dd> : null}
        </div>
      ))}
    </dl>
  );
}

function Facts({ items }: { items: [string, string][] }) {
  return (
    <dl className="divide-y text-sm">
      {items.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-4 py-2 first:pt-0">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="font-medium tabular-nums">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Bars({
  rows,
  total,
  empty,
  heading,
}: {
  rows: { label: string; value: number }[];
  total: number;
  empty: string;
  heading?: string;
}) {
  if (total === 0) return empty ? <p className="text-muted-foreground text-sm">{empty}</p> : null;
  const shown = rows.filter((r) => r.value > 0);
  return (
    <div className="flex flex-col gap-3">
      {heading ? (
        <h4 className="text-muted-foreground font-mono text-[11px] tracking-[0.15em] uppercase">
          {heading}
        </h4>
      ) : null}
      <ul className="flex flex-col gap-3">
        {shown.map((r) => {
          const share = percent(r.value, total) ?? 0;
          return (
            <li key={r.label} className="flex flex-col gap-1.5 text-sm">
              <div className="flex items-baseline justify-between gap-4">
                <span>{r.label}</span>
                <span className="tabular-nums">
                  <span className="font-medium">{r.value}</span>
                  <span className="text-muted-foreground"> · {share}%</span>
                </span>
              </div>
              <div aria-hidden className="bg-foreground/[0.07] h-1.5 overflow-hidden rounded-full">
                <div className="bg-brand h-full rounded-full" style={{ width: `${share}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Funnel({ steps }: { steps: [string, number][] }) {
  const first = steps[0]?.[1] ?? 0;
  if (first === 0)
    return <p className="text-muted-foreground text-sm">No quotes in this period.</p>;
  return (
    <ol className="flex flex-col gap-3">
      {steps.map(([name, value]) => {
        const share = percent(value, first) ?? 0;
        return (
          <li key={name} className="flex flex-col gap-1.5 text-sm">
            <div className="flex items-baseline justify-between gap-4">
              <span>{name}</span>
              <span className="font-medium tabular-nums">{value}</span>
            </div>
            <div aria-hidden className="bg-foreground/[0.07] h-1.5 overflow-hidden rounded-full">
              <div className="bg-brand h-full rounded-full" style={{ width: `${share}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
