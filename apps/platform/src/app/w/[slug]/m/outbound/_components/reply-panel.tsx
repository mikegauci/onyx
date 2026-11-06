import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import type { ConversationDetail } from "@/lib/inbox";
import { type DraftDetail, outboundPath } from "@/lib/outbound";

import { DraftCard, NewDraftForm } from "./draft-card";

/** The conversation's reply waiting for approval (or its latest one), and a form to write one. */
export async function ReplyPanel({
  slug,
  conversation,
  permissions,
  modules,
  timezone,
  path,
}: {
  slug: string;
  conversation: ConversationDetail;
  permissions: readonly string[];
  modules: readonly string[];
  timezone: string;
  path: string;
}) {
  const drafts = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/outbound/drafts", {
        params: { path: { slug }, query: { conversation_id: conversation.id } },
      }),
    ),
    path,
  );
  const latest = drafts[0];
  let detail: DraftDetail | null = null;
  if (latest) {
    detail = requireOk(
      await withApi((api) =>
        api.GET("/v1/w/{slug}/outbound/drafts/{draft_id}", {
          params: { path: { slug, draft_id: latest.id } },
        }),
      ),
      path,
    );
  }
  const open = detail !== null && (detail.status === "pending" || detail.status === "approved");
  const canWrite = permissions.includes("outbound.write") && conversation.status !== "closed";

  let quotes: { id: string; label: string }[] = [];
  if (canWrite && !open && conversation.contact && modules.includes("quotations")) {
    const result = await withApi((api) =>
      api.GET("/v1/w/{slug}/quotations/quotes", {
        params: { path: { slug }, query: { contact_id: conversation.contact!.id, limit: 50 } },
      }),
    );
    if (result.ok) {
      quotes = result.data.items
        .filter((q) => q.status === "draft" || q.status === "approved")
        .map((q) => ({ id: q.id, label: `${q.number} · ${q.title} (${q.status})` }));
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-md border p-3" aria-labelledby="reply-heading">
      <h3 id="reply-heading" className="font-medium">
        Reply for approval
      </h3>
      <p className="text-muted-foreground text-xs">
        Replies go to the customer only after an admin or owner approves the exact text, and any
        quote with it.
      </p>
      {detail ? (
        <DraftCard slug={slug} draft={detail} permissions={permissions} timezone={timezone} />
      ) : null}
      {canWrite && !open ? (
        <div className="flex flex-col gap-2">
          {detail ? <h4 className="text-sm font-medium">New reply</h4> : null}
          <NewDraftForm slug={slug} conversationId={conversation.id} quotes={quotes} />
        </div>
      ) : null}
      {conversation.status === "closed" && !open ? (
        <p className="text-muted-foreground text-xs">Reopen the conversation to write a reply.</p>
      ) : null}
      <Link className="text-xs underline" href={outboundPath(slug)}>
        All replies waiting for approval
      </Link>
    </section>
  );
}
