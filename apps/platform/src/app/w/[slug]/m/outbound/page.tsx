import { PageHeader } from "@onyx/ui/components/page";
import { Badge } from "@onyx/ui/components/badge";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { inboxPath } from "@/lib/inbox";
import {
  type Draft,
  DRAFT_STATUS_LABEL,
  DRAFT_STATUS_VARIANT,
  originLabel,
  outboundPath,
} from "@/lib/outbound";
import { workspaceWith } from "@/lib/settings-guard";

import { ExpiryForm } from "./_components/draft-card";

function DraftList({
  slug,
  label,
  drafts,
  timezone,
  empty,
}: {
  slug: string;
  label: string;
  drafts: Draft[];
  timezone: string;
  empty: string;
}) {
  if (drafts.length === 0) {
    return (
      <p className="text-muted-foreground rounded-2xl border border-dashed px-5 py-4 text-sm">
        {empty}
      </p>
    );
  }
  return (
    <ul className="bg-card divide-y rounded-2xl border" aria-label={label}>
      {drafts.map((draft) => (
        <li key={draft.id} className="flex flex-col gap-1.5 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Link
              className="hover:text-brand font-medium underline-offset-4 transition-colors hover:underline"
              href={outboundPath(slug, "drafts", draft.id)}
            >
              {draft.conversation_subject || "Conversation"}
            </Link>
            <Badge variant={DRAFT_STATUS_VARIANT[draft.status]}>
              {DRAFT_STATUS_LABEL[draft.status]}
            </Badge>
          </div>
          <p className="text-muted-foreground line-clamp-2 text-sm whitespace-pre-wrap">
            {draft.body}
          </p>
          <p className="text-muted-foreground text-xs">
            {originLabel(draft)}
            {draft.quote ? ` · quote ${draft.quote.number}` : ""} ·{" "}
            <time dateTime={draft.created_at}>{formatInZone(draft.created_at, timezone)}</time>
          </p>
          {draft.quote?.blocked ? <p className="text-xs">{draft.quote.blocked.message}</p> : null}
          {draft.expiry ? <p className="text-xs">{draft.expiry.message}</p> : null}
        </li>
      ))}
    </ul>
  );
}

export default async function OutboundPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = outboundPath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "outbound" } } }),
    ),
    path,
  );
  const workspace = await workspaceWith(slug, "outbound.read", path);
  const list = (status: Draft["status"]) =>
    withApi((api) =>
      api.GET("/v1/w/{slug}/outbound/drafts", {
        params: { path: { slug }, query: { status } },
      }),
    );
  const [pending, approved, sent, settings] = await Promise.all([
    list("pending"),
    list("approved"),
    list("sent"),
    withApi((api) => api.GET("/v1/w/{slug}/outbound/settings", { params: { path: { slug } } })),
  ]);
  const zone = workspace.timezone;
  const canApprove = workspace.permissions.includes("outbound.approve");
  const canManage = workspace.permissions.includes("outbound.manage");
  const outboundSettings = requireOk(settings, path);
  const hours = outboundSettings.expiry_hours;

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <PageHeader
        eyebrow="Module"
        title="Outbound replies"
        description={
          <>
            Replies drafted by staff or the{" "}
            <Link
              className="text-brand underline-offset-4 hover:underline"
              href={inboxPath(slug, "conversations")}
            >
              assistant
            </Link>{" "}
            go to the customer only after an admin or owner approves the exact text. A reply with a
            quote needs that quote approved first. Drafts stay valid for {hours} hours, and expire
            sooner if the customer writes again or the quote changes.
            {!canApprove ? (
              <span className="mt-2 block text-xs">
                Admins and owners approve replies. You can draft, edit and send approved ones.
              </span>
            ) : null}
          </>
        }
      />

      <section className="flex flex-col gap-3" aria-labelledby="pending-heading">
        <h2 id="pending-heading" className="text-lg font-light tracking-tight">
          Waiting for approval
        </h2>
        <DraftList
          slug={slug}
          label="Waiting for approval"
          drafts={requireOk(pending, path)}
          timezone={zone}
          empty="Nothing is waiting for approval."
        />
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="approved-heading">
        <h2 id="approved-heading" className="text-lg font-light tracking-tight">
          Approved, ready to send
        </h2>
        <DraftList
          slug={slug}
          label="Approved, ready to send"
          drafts={requireOk(approved, path)}
          timezone={zone}
          empty="No approved replies are waiting to be sent."
        />
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="sent-heading">
        <h2 id="sent-heading" className="text-lg font-light tracking-tight">
          Recently sent
        </h2>
        <DraftList
          slug={slug}
          label="Recently sent"
          drafts={requireOk(sent, path).slice(0, 10)}
          timezone={zone}
          empty="No replies sent yet."
        />
      </section>

      {canManage ? (
        <section className="flex flex-col gap-3" aria-labelledby="expiry-heading">
          <h2 id="expiry-heading" className="text-lg font-light tracking-tight">
            Draft expiry and reminders
          </h2>
          <ExpiryForm slug={slug} settings={outboundSettings} />
        </section>
      ) : null}
    </div>
  );
}
