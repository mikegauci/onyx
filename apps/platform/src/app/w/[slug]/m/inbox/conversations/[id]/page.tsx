import { Badge } from "@onyx/ui/components/badge";
import { Panel } from "@onyx/ui/components/page";
import { cn } from "@onyx/ui/lib/utils";
import {
  ArrowLeft,
  Bot,
  Clock,
  type LucideIcon,
  Mail,
  MessageCircle,
  MessageSquare,
  Phone,
  StickyNote,
} from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { type AssistantRun, assistantPaused } from "@/lib/assistant";
import { crmPath, formatInZone } from "@/lib/crm";
import { getControls, getMe } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import {
  DELIVERY_LABEL,
  DELIVERY_VARIANT,
  deliveryBlocksAddress,
  describeEvent,
  inboxPath,
  type Message,
  messageHeading,
  replyWindow,
  STATUS_LABEL,
  STATUS_VARIANT,
  WHATSAPP_STATUS_LABEL,
  WHATSAPP_STATUS_VARIANT,
} from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { Pager } from "../../../crm/_components/list-controls";
import { contactOptions, param, recordId, type SearchParams } from "../../../crm/data";
import { ReplyPanel } from "../../../outbound/_components/reply-panel";
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
  const controls = await getControls(slug);
  if (canRunAssistant) {
    const result = await withApi((api) =>
      api.GET("/v1/w/{slug}/assistant/conversations/{conversation_id}/runs", { params: ids }),
    );
    runs = requireOk(result, path).slice(0, 5);
  }
  // Shown when the module is on; the API checks the module and permissions on every request.
  const showReplies =
    workspace.modules.includes("outbound") && workspace.permissions.includes("outbound.read");
  const whatsapp = record.channel.kind === "whatsapp";
  const replyTime = replyWindow(record.reply_window_closes_at, new Date());
  // The API returns newest first; read the conversation top to bottom.
  const timeline = [...page.items].reverse();

  const channelIcon = CHANNEL_ICON[record.channel.kind] ?? MessageSquare;
  const ChannelIcon = channelIcon;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <Link
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex items-center gap-1.5 self-start rounded-sm text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
          href={inboxPath(slug, "conversations")}
        >
          <ArrowLeft aria-hidden className="size-4" />
          Back to conversations
        </Link>
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex min-w-0 flex-col gap-3">
            <h2 className="text-2xl font-light tracking-[-0.02em] text-balance">
              {record.subject}
            </h2>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
              <Badge variant={STATUS_VARIANT[record.status]}>{STATUS_LABEL[record.status]}</Badge>
              <span className="font-medium">{record.customer_label}</span>
              <span className="text-muted-foreground inline-flex items-center gap-1.5">
                <ChannelIcon aria-hidden className="size-3.5" />
                {record.channel.name}
              </span>
              {record.handler === "assistant" ? (
                <Badge variant="brand">
                  <Bot aria-hidden />
                  Assistant
                </Badge>
              ) : null}
              {record.contact ? (
                <Link
                  className="text-brand underline-offset-4 hover:underline"
                  href={crmPath(slug, "contacts", record.contact.id)}
                >
                  View contact
                </Link>
              ) : null}
              {record.lead ? (
                <Link
                  className="text-brand underline-offset-4 hover:underline"
                  href={crmPath(slug, "leads", record.lead.id)}
                >
                  Lead: {record.lead.title}
                </Link>
              ) : null}
            </div>
          </div>
          {staff ? <StatusForm slug={slug} conversation={record} /> : null}
        </div>
      </div>

      {whatsapp ? (
        <p
          role="note"
          className={cn(
            "flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm",
            replyTime.open
              ? "border-success/25 bg-success/[0.06]"
              : "border-warning/30 bg-warning/[0.07]",
          )}
        >
          <Clock
            aria-hidden
            className={cn(
              "mt-0.5 size-4 shrink-0",
              replyTime.open ? "text-success" : "text-warning",
            )}
          />
          <span>
            {replyTime.open ? (
              <>
                WhatsApp allows a free-text reply until{" "}
                <time dateTime={replyTime.closesAt} className="font-medium">
                  {formatInZone(replyTime.closesAt, zone)}
                </time>
                , 24 hours after the customer&apos;s last message. After that, only an approved
                template can be sent.
              </>
            ) : (
              <>
                The 24-hour WhatsApp reply window is closed. Only an approved template can be sent
                until the customer writes again.
              </>
            )}
          </span>
        </p>
      ) : null}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_24rem]">
        <section
          className="bg-card flex min-w-0 flex-col rounded-2xl border"
          aria-labelledby="messages-heading"
        >
          <div className="flex items-center justify-between gap-3 border-b px-5 py-3">
            <h3 id="messages-heading" className="text-sm font-medium">
              Messages
            </h3>
            <Pager base={path} params={{}} cursor={cursor} nextCursor={page.next_cursor} />
          </div>
          {timeline.length === 0 ? (
            <p className="text-muted-foreground p-5 text-sm">No messages.</p>
          ) : (
            <ol className="flex flex-col gap-5 p-4 sm:p-5" aria-label="Messages">
              {timeline.map((message) => (
                <MessageItem key={message.id} message={message} zone={zone} />
              ))}
            </ol>
          )}
          {canWrite ? (
            <div className="bg-background/40 border-t p-4 sm:p-5">
              <ComposeForm slug={slug} conversation={record} />
            </div>
          ) : null}
        </section>

        <aside className="flex min-w-0 flex-col gap-4" aria-label="Conversation details">
          {showReplies ? (
            <ReplyPanel
              slug={slug}
              conversation={record}
              permissions={workspace.permissions}
              modules={workspace.modules}
              timezone={zone}
              path={path}
              whatsappWindowOpen={whatsapp ? replyTime.open : null}
            />
          ) : null}
          {canRunAssistant ? (
            <AssistantPanel
              slug={slug}
              conversationId={record.id}
              status={record.status}
              runs={runs}
              timezone={zone}
              paused={assistantPaused(controls.ok ? controls.data : null)}
            />
          ) : null}
          <Panel title="Details" as="h3" divided={false}>
            {staff ? (
              <div className="flex flex-col gap-5 [&>*+*]:border-t [&>*+*]:pt-5">
                <AssignForm
                  slug={slug}
                  conversation={record}
                  assignees={staff.assignees}
                  me={staff.me}
                />
                <HandoffForm slug={slug} conversation={record} canManage={canManage} />
                <LinkContactForm slug={slug} conversation={record} contacts={contacts} />
              </div>
            ) : (
              <p className="text-sm">Assigned to {record.assignee?.display_name ?? "nobody"}</p>
            )}
          </Panel>
          <Panel title="History" as="h3" divided={false}>
            <ol className="flex flex-col gap-4" aria-label="History">
              {history.items.map((event) => (
                <li key={event.id} className="relative pl-5 text-sm">
                  <span
                    aria-hidden
                    className="bg-foreground/25 absolute top-1.5 left-0 size-2 rounded-full"
                  />
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
          </Panel>
        </aside>
      </div>
    </div>
  );
}

const CHANNEL_ICON: Record<string, LucideIcon> = {
  whatsapp: MessageCircle,
  email: Mail,
  manual: Phone,
};

/** One message: customer on the left, staff on the right, internal notes full width. */
function MessageItem({ message, zone }: { message: Message; zone: string }) {
  const note = message.direction === "note";
  const outbound = message.direction === "outbound";
  const assistant = note && message.author_kind === "assistant";
  const NoteIcon = assistant ? Bot : StickyNote;
  return (
    <li className={cn("flex flex-col gap-1.5", outbound ? "items-end" : "items-start")}>
      <p
        className={cn(
          "text-muted-foreground flex items-center gap-1.5 px-1 text-xs",
          outbound && "flex-row-reverse",
        )}
      >
        {note ? <NoteIcon aria-hidden className="size-3.5" /> : null}
        <span className="text-foreground/90 font-medium">{messageHeading(message)}</span>
        <span aria-hidden>·</span>
        <time dateTime={message.occurred_at}>{formatInZone(message.occurred_at, zone)}</time>
      </p>
      <div
        className={cn(
          "text-sm break-words whitespace-pre-wrap",
          note
            ? "w-full rounded-xl border border-dashed px-4 py-3"
            : "max-w-[85%] rounded-2xl border px-4 py-2.5",
          message.direction === "inbound" && "bg-background rounded-tl-md",
          outbound && "border-brand/25 bg-brand/10 rounded-tr-md",
          assistant && "border-brand/30 bg-brand/[0.04]",
          note && !assistant && "bg-warning/[0.04] border-warning/25",
        )}
      >
        {message.body}
      </div>
      {message.delivery_status === "logged" && outbound ? (
        <p className="text-muted-foreground px-1 text-xs">
          Logged only: recorded, not sent by Onyx
        </p>
      ) : null}
      {message.delivery ? (
        <div className="flex flex-col gap-1 px-1 text-xs">
          <p className="flex flex-wrap items-center gap-2">
            <Badge variant={DELIVERY_VARIANT[message.delivery.status]}>
              {DELIVERY_LABEL[message.delivery.status]}
            </Badge>
            <span className="text-muted-foreground">
              Emailed to {message.delivery.recipient} ·{" "}
              <time dateTime={message.delivery.status_at}>
                {formatInZone(message.delivery.status_at, zone)}
              </time>
            </span>
          </p>
          {deliveryBlocksAddress(message.delivery.status) ? (
            <p role="note" className="bg-warning/15 rounded-md px-2 py-1">
              Onyx will not email this address again until it is released under Blocked addresses.
            </p>
          ) : null}
        </div>
      ) : null}
      {message.whatsapp ? (
        <p
          className={cn(
            "flex flex-wrap items-center gap-2 px-1 text-xs",
            outbound && "justify-end",
          )}
        >
          <Badge variant={WHATSAPP_STATUS_VARIANT[message.whatsapp.status]}>
            {WHATSAPP_STATUS_LABEL[message.whatsapp.status]}
          </Badge>
          <span className="text-muted-foreground">
            WhatsApp to {message.whatsapp.recipient}
            {message.whatsapp.template_name ? ` · template ${message.whatsapp.template_name}` : ""}
            {message.whatsapp.status === "failed" && message.whatsapp.detail
              ? ` · Meta error ${message.whatsapp.detail}`
              : ""}{" "}
            ·{" "}
            <time dateTime={message.whatsapp.status_at}>
              {formatInZone(message.whatsapp.status_at, zone)}
            </time>
          </span>
        </p>
      ) : null}
    </li>
  );
}

async function loadAssignees(slug: string, path: string) {
  return requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/inbox/assignees", { params: { path: { slug } } })),
    path,
  ).items;
}
