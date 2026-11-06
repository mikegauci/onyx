import { Badge } from "@onyx/ui/components/badge";
import { cn } from "@onyx/ui/lib/utils";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import type { AssistantRun } from "@/lib/assistant";
import { crmPath, formatInZone } from "@/lib/crm";
import { getMe } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import {
  describeEvent,
  inboxPath,
  messageHeading,
  STATUS_LABEL,
  STATUS_VARIANT,
} from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { Pager } from "../../../crm/_components/list-controls";
import { contactOptions, param, recordId, type SearchParams } from "../../../crm/data";
import { AssistantPanel } from "../../_components/assistant-panel";
import {
  AssignForm,
  ComposeForm,
  HandoffForm,
  LinkContactForm,
  StatusForm,
} from "../../_components/forms";

export default async function ConversationPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>;
  searchParams: SearchParams;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = inboxPath(slug, "conversations", id);
  const workspace = await workspaceWith(slug, "inbox.read", path);
  const cursor = param((await searchParams).cursor);
  const ids = { path: { slug, conversation_id: id } };
  const [conversation, messages, events] = await Promise.all([
    withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/conversations/{conversation_id}", { params: ids }),
    ),
    withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/conversations/{conversation_id}/messages", {
        params: { ...ids, query: { cursor } },
      }),
    ),
    withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/conversations/{conversation_id}/events", {
        params: { ...ids, query: { limit: 20 } },
      }),
    ),
  ]);
  const record = requireOk(conversation, path);
  const page = requireOk(messages, path);
  const history = requireOk(events, path);
  const canWrite = workspace.permissions.includes("inbox.write");
  const canManage = workspace.permissions.includes("inbox.manage");
  const zone = workspace.timezone;

  let staff: { assignees: Awaited<ReturnType<typeof loadAssignees>>; me: string } | null = null;
  let contacts: Awaited<ReturnType<typeof contactOptions>> = [];
  if (canWrite) {
    const [assignees, me, options] = await Promise.all([
      loadAssignees(slug, path),
      getMe(),
      contactOptions(slug),
    ]);
    staff = { assignees, me: requireOk(me, path).user.id };
    contacts = options;
  }
  // The panel is a convenience; the API still checks the module and permission on every run.
  const canRunAssistant =
    workspace.modules.includes("assistant") && workspace.permissions.includes("assistant.run");
  let runs: AssistantRun[] = [];
  if (canRunAssistant) {
    const result = await withApi((api) =>
      api.GET("/v1/w/{slug}/assistant/conversations/{conversation_id}/runs", { params: ids }),
    );
    runs = requireOk(result, path).slice(0, 5);
  }
  // The API returns newest first; read the conversation top to bottom.
  const timeline = [...page.items].reverse();

  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm underline" href={inboxPath(slug, "conversations")}>
        Back to conversations
      </Link>
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-medium">{record.subject}</h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant={STATUS_VARIANT[record.status]}>{STATUS_LABEL[record.status]}</Badge>
          <span>{record.customer_label}</span>
          <span className="text-muted-foreground">· {record.channel.name}</span>
          {record.contact ? (
            <Link className="underline" href={crmPath(slug, "contacts", record.contact.id)}>
              View contact
            </Link>
          ) : null}
          {record.lead ? (
            <Link className="underline" href={crmPath(slug, "leads", record.lead.id)}>
              Lead: {record.lead.title}
            </Link>
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section className="flex flex-col gap-4" aria-labelledby="messages-heading">
          <h3 id="messages-heading" className="font-medium">
            Messages
          </h3>
          <Pager base={path} params={{}} cursor={cursor} nextCursor={page.next_cursor} />
          {timeline.length === 0 ? (
            <p className="text-muted-foreground text-sm">No messages.</p>
          ) : (
            <ol className="flex flex-col gap-3" aria-label="Messages">
              {timeline.map((message) => (
                <li
                  key={message.id}
                  className={cn(
                    "rounded-md border p-3",
                    message.direction === "outbound" && "bg-secondary/40 ml-8",
                    message.direction === "note" && "border-dashed bg-transparent",
                    message.direction === "note" &&
                      message.author_kind === "assistant" &&
                      "border-primary/40 bg-primary/5",
                  )}
                >
                  <p className="text-sm font-medium">{messageHeading(message)}</p>
                  <p className="text-sm whitespace-pre-wrap">{message.body}</p>
                  <p className="text-muted-foreground text-xs">
                    <time dateTime={message.occurred_at}>
                      {formatInZone(message.occurred_at, zone)}
                    </time>
                    {message.delivery_status === "logged" && message.direction === "outbound"
                      ? " · recorded, not sent by Onyx"
                      : ""}
                  </p>
                </li>
              ))}
            </ol>
          )}
          {canWrite ? <ComposeForm slug={slug} conversation={record} /> : null}
        </section>

        <aside className="flex flex-col gap-6" aria-label="Conversation details">
          {canRunAssistant ? (
            <AssistantPanel
              slug={slug}
              conversationId={record.id}
              status={record.status}
              runs={runs}
              timezone={zone}
            />
          ) : null}
          {staff ? (
            <>
              <StatusForm slug={slug} conversation={record} />
              <AssignForm
                slug={slug}
                conversation={record}
                assignees={staff.assignees}
                me={staff.me}
              />
              <HandoffForm slug={slug} conversation={record} canManage={canManage} />
              <LinkContactForm slug={slug} conversation={record} contacts={contacts} />
            </>
          ) : (
            <p className="text-sm">Assigned to {record.assignee?.display_name ?? "nobody"}</p>
          )}
          <section className="flex flex-col gap-2" aria-labelledby="history-heading">
            <h3 id="history-heading" className="font-medium">
              History
            </h3>
            <ol className="flex flex-col gap-2" aria-label="History">
              {history.items.map((event) => (
                <li key={event.id} className="border-l-2 pl-3 text-sm">
                  <p>{describeEvent(event)}</p>
                  <p className="text-muted-foreground text-xs">
                    {event.actor?.display_name ?? (event.actor ? "Former member" : "System")} ·{" "}
                    <time dateTime={event.occurred_at}>
                      {formatInZone(event.occurred_at, zone)}
                    </time>
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}

async function loadAssignees(slug: string, path: string) {
  return requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/inbox/assignees", { params: { path: { slug } } })),
    path,
  ).items;
}
