import { EmptyState } from "@onyx/ui/components/states";
import { Repeat } from "lucide-react";
import Link from "next/link";

import { MATCH_STATUS_LABEL, type MatchStatus } from "@/lib/alerts";
import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { param, type SearchParams } from "../../crm/data";
import { FollowupList } from "../_components/alerts";

const STATUSES: MatchStatus[] = ["pending", "skipped", "sent", "dismissed"];

export default async function FollowupsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = automotivePath(slug, "follow-ups");
  const workspace = await workspaceWith(slug, "crm.read", path);
  const raw = param((await searchParams).status, 20);
  const status = STATUSES.includes(raw as MatchStatus) ? (raw as MatchStatus) : "pending";
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/followups", {
        params: { path: { slug }, query: { status, limit: 100 } },
      }),
    ),
    path,
  );
  return (
    <section className="flex flex-col gap-4" aria-labelledby="followups-heading">
      <h2 id="followups-heading" className="sr-only">
        Sold-car follow-ups
      </h2>
      <nav aria-label="Follow-up status" className="flex flex-wrap gap-2 text-sm">
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={`${path}?status=${s}`}
            aria-current={s === status ? "page" : undefined}
            className={
              s === status
                ? "bg-foreground text-background rounded-full px-3 py-1"
                : "hover:bg-foreground/[0.05] rounded-full border px-3 py-1"
            }
          >
            {MATCH_STATUS_LABEL[s]}
          </Link>
        ))}
        <span className="text-muted-foreground ml-auto self-center font-mono text-[11px] tracking-[0.15em] uppercase">
          {page.total} follow-ups
        </span>
      </nav>
      <p className="text-muted-foreground max-w-prose text-sm">
        When a car is sold, people who asked about it in the last 30 days (not the buyer) are
        offered up to three similar cars: same make and body, price within 20% and year within two.
        Within 24 hours of their last WhatsApp message the reply is a normal message; after that it
        uses the car-alert template and needs their consent.
      </p>
      {page.items.length === 0 ? (
        <EmptyState
          icon={Repeat}
          title="No follow-ups"
          description="They appear here when a car someone asked about is sold."
        />
      ) : (
        <FollowupList
          slug={slug}
          items={page.items}
          canSend={workspace.permissions.includes("outbound.approve")}
          canWrite={workspace.permissions.includes("crm.write")}
        />
      )}
    </section>
  );
}
