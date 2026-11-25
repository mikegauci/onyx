import { EmptyState } from "@onyx/ui/components/states";
import { BellRing } from "lucide-react";
import Link from "next/link";

import { type MatchStatus, MATCH_STATUS_LABEL } from "@/lib/alerts";
import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { param, recordId, type SearchParams } from "../../crm/data";
import { MatchList } from "../_components/alerts";

const STATUSES: MatchStatus[] = ["pending", "skipped", "sent", "dismissed"];

export default async function MatchesPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = automotivePath(slug, "matches");
  const workspace = await workspaceWith(slug, "crm.read", path);
  const search = await searchParams;
  const raw = param(search.status, 20);
  const status = STATUSES.includes(raw as MatchStatus) ? (raw as MatchStatus) : "pending";
  const rawLead = param(search.lead_id, 40);
  const leadId = rawLead ? recordId(rawLead) : undefined;
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/matches", {
        params: { path: { slug }, query: { status, lead_id: leadId, limit: 100 } },
      }),
    ),
    path,
  );
  const canSend = workspace.permissions.includes("outbound.approve");
  return (
    <section className="flex flex-col gap-4" aria-labelledby="matches-heading">
      <h2 id="matches-heading" className="sr-only">
        Matches
      </h2>
      <nav aria-label="Match status" className="flex flex-wrap gap-2 text-sm">
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={`${path}?status=${s}${leadId ? `&lead_id=${leadId}` : ""}`}
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
          {page.total} matches
        </span>
      </nav>
      <p className="text-muted-foreground text-sm">
        Cars in stock that meet what a buyer asked for. Alerts go out on WhatsApp only when you send
        them, and only to customers who agreed to car alerts. Each buyer is offered a car once.
        {canSend ? "" : " An admin or owner sends them."}
      </p>
      {page.items.length === 0 ? (
        <EmptyState
          icon={BellRing}
          title="No matches"
          description="Record what a buyer wants on their lead. Matching cars appear here after each import."
        />
      ) : (
        <MatchList
          slug={slug}
          items={page.items}
          canSend={canSend}
          canWrite={workspace.permissions.includes("crm.write")}
        />
      )}
    </section>
  );
}
