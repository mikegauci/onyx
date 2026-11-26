import { EmptyState } from "@onyx/ui/components/states";
import { Star } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";
import { REVIEW_STATUS_LABEL, REVIEW_STATUSES, type ReviewStatus } from "@/lib/reviews";
import { workspaceWith } from "@/lib/settings-guard";

import { param, type SearchParams } from "../../crm/data";
import { ReviewRequestList } from "../_components/reviews";

export default async function ReviewRequestsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = dealsPath(slug, "reviews");
  const workspace = await workspaceWith(slug, "deals.read", path);
  const raw = param((await searchParams).status, 20);
  const status = REVIEW_STATUSES.includes(raw as ReviewStatus) ? (raw as ReviewStatus) : "pending";
  const [page, settings] = await Promise.all([
    withApi((api) =>
      api.GET("/v1/w/{slug}/deals/reviews", {
        params: { path: { slug }, query: { status, limit: 100 } },
      }),
    ),
    withApi((api) =>
      api.GET("/v1/w/{slug}/deals/reviews/settings", { params: { path: { slug } } }),
    ),
  ]);
  const list = requireOk(page, path);
  const config = requireOk(settings, path);
  const canManage = workspace.permissions.includes("deals.manage");
  return (
    <section className="flex flex-col gap-4" aria-labelledby="reviews-heading">
      <h2 id="reviews-heading" className="sr-only">
        Review requests
      </h2>
      <nav aria-label="Review request status" className="flex flex-wrap gap-2 text-sm">
        {REVIEW_STATUSES.map((s) => (
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
            {REVIEW_STATUS_LABEL[s]}
          </Link>
        ))}
        <span className="text-muted-foreground ml-auto self-center font-mono text-[11px] tracking-[0.15em] uppercase">
          {list.total} requests
        </span>
      </nav>
      <p className="text-muted-foreground max-w-prose text-sm">
        {config.delay_days} days after a deal is collected, the customer appears here once. Sending
        uses WhatsApp when they have written to you (the template after 24 hours), otherwise email.
        Customers who opted out are not messaged.
      </p>
      {!config.enabled ? (
        <p className="text-sm">
          Review requests are off.{" "}
          {canManage ? (
            <Link href={dealsPath(slug, "settings")} className="underline underline-offset-4">
              Add your Google review link in Settings.
            </Link>
          ) : (
            "An owner or admin adds the Google review link in Settings."
          )}
        </p>
      ) : null}
      {list.items.length === 0 ? (
        <EmptyState
          icon={Star}
          title="No review requests"
          description="They appear here a few days after each car is collected."
        />
      ) : (
        <ReviewRequestList
          slug={slug}
          items={list.items}
          canSend={workspace.permissions.includes("outbound.approve")}
          canWrite={workspace.permissions.includes("deals.write")}
          timezone={workspace.timezone}
        />
      )}
    </section>
  );
}
