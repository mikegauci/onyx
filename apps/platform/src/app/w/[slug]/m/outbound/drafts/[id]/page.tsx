import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { outboundPath } from "@/lib/outbound";
import { workspaceWith } from "@/lib/settings-guard";

import { recordId } from "../../../crm/data";
import { DraftCard } from "../../_components/draft-card";

export default async function DraftPage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = outboundPath(slug, "drafts", id);
  const workspace = await workspaceWith(slug, "outbound.read", path);
  const draft = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/outbound/drafts/{draft_id}", {
        params: { path: { slug, draft_id: id } },
      }),
    ),
    path,
  );

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <Link
        className="text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline"
        href={outboundPath(slug)}
      >
        Back to outbound replies
      </Link>
      <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
        Reply: {draft.conversation_subject || "Conversation"}
      </h1>
      <div className="bg-card rounded-2xl border p-5 sm:p-6">
        <DraftCard
          slug={slug}
          draft={draft}
          permissions={workspace.permissions}
          timezone={workspace.timezone}
          showConversation
        />
      </div>
    </div>
  );
}
