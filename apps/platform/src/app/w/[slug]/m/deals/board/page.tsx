import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Input } from "@onyx/ui/components/input";
import { EmptyState } from "@onyx/ui/components/states";
import { Plus } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { euros } from "@/lib/automotive";
import { getWorkspace } from "@/lib/data";
import { BOARD_STAGES, type DealSummary, dealsPath, STAGE_LABEL, STAGE_VARIANT } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const FOCUS = "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none";

export default async function DealsBoardPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const query = await searchParams;
  const q = typeof query.q === "string" ? query.q : "";
  const closed = query.closed === "1";
  const path = dealsPath(slug, "board");
  const workspace = requireOk(await getWorkspace(slug), path);
  const data = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals", {
        params: { path: { slug }, query: { q: q || undefined, include_closed: closed } },
      }),
    ),
    path,
  );
  const canWrite = workspace.permissions.includes("deals.write");
  const byStage = new Map(BOARD_STAGES.map((s) => [s, [] as DealSummary[]]));
  const finished: DealSummary[] = [];
  for (const deal of data.items) {
    const column = byStage.get(deal.stage);
    if (column) column.push(deal);
    else finished.push(deal);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <form className="flex gap-2" role="search">
          <label htmlFor="deal-search" className="sr-only">
            Search deals
          </label>
          <Input
            id="deal-search"
            name="q"
            defaultValue={q}
            placeholder="Search deals"
            className="w-56"
          />
          {closed ? <input type="hidden" name="closed" value="1" /> : null}
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
        <div className="flex items-center gap-3">
          <Link
            href={closed ? path : `${path}?closed=1`}
            className={`${FOCUS} text-muted-foreground hover:text-foreground rounded-sm text-sm`}
          >
            {closed ? "Hide finished deals" : "Show finished deals"}
          </Link>
          {canWrite ? (
            <Button asChild>
              <Link href={dealsPath(slug, "new")}>
                <Plus aria-hidden />
                New deal
              </Link>
            </Button>
          ) : null}
        </div>
      </div>

      {data.items.length === 0 ? (
        <EmptyState
          title={q ? "No matching deals" : "No deals yet"}
          description="A deal follows one sale from reservation to collection, with the customer's documents."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {BOARD_STAGES.map((stage) => {
            const deals = byStage.get(stage) ?? [];
            return (
              <section
                key={stage}
                aria-labelledby={`stage-${stage}`}
                className="bg-foreground/[0.02] flex flex-col gap-3 rounded-2xl border p-3"
              >
                <h2
                  id={`stage-${stage}`}
                  className="flex items-center justify-between px-1 text-sm font-medium"
                >
                  {STAGE_LABEL[stage]}
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {deals.length}
                  </span>
                </h2>
                <ul className="flex flex-col gap-2" aria-label={STAGE_LABEL[stage]}>
                  {deals.map((deal) => (
                    <li key={deal.id}>
                      <DealCard slug={slug} deal={deal} />
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}

      {finished.length > 0 ? (
        <section aria-labelledby="finished-heading" className="flex flex-col gap-3">
          <h2 id="finished-heading" className="text-sm font-medium">
            Finished deals
          </h2>
          <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" aria-label="Finished deals">
            {finished.map((deal) => (
              <li key={deal.id}>
                <DealCard slug={slug} deal={deal} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function DealCard({ slug, deal }: { slug: string; deal: DealSummary }) {
  const complete = deal.documents_total > 0 && deal.documents_verified === deal.documents_total;
  return (
    <Link
      href={dealsPath(slug, deal.id)}
      className={`${FOCUS} bg-card hover:border-foreground/20 flex flex-col gap-2 rounded-xl border p-3 text-sm transition-colors`}
    >
      <span className="font-medium">{deal.title}</span>
      {deal.vehicle ? <span className="text-muted-foreground">{deal.vehicle.label}</span> : null}
      <span className="flex flex-wrap items-center gap-2">
        {deal.stage === "collected" || deal.stage === "cancelled" ? (
          <Badge variant={STAGE_VARIANT[deal.stage]}>{STAGE_LABEL[deal.stage]}</Badge>
        ) : null}
        <Badge variant={complete ? "success" : deal.documents_missing > 0 ? "warning" : "info"}>
          Documents {deal.documents_verified}/{deal.documents_total}
        </Badge>
        {deal.price_cents !== null ? (
          <span className="text-muted-foreground tabular-nums">{euros(deal.price_cents)}</span>
        ) : null}
      </span>
    </Link>
  );
}
