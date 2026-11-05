import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { inboxPath } from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { contactOptions } from "../../../crm/data";
import { NewConversationForm } from "../../_components/forms";

export default async function NewConversationPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const path = inboxPath(slug, "conversations", "new");
  await workspaceWith(slug, "inbox.write", path);
  const channels = requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/inbox/channels", { params: { path: { slug } } })),
    path,
  ).items.filter((c) => c.connected);
  const contacts = await contactOptions(slug);

  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm underline" href={inboxPath(slug, "conversations")}>
        Back to conversations
      </Link>
      <h2 className="text-xl font-medium">New conversation</h2>
      {channels.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          There is no phone / in-person channel yet. An admin can add one under Channels.
        </p>
      ) : (
        <NewConversationForm slug={slug} channels={channels} contacts={contacts} />
      )}
    </div>
  );
}
