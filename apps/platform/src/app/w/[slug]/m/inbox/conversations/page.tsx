import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { EmptyState } from "@onyx/ui/components/states";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";
import { cn } from "@onyx/ui/lib/utils";
import { Inbox } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import {
  type ConversationStatus,
  inboxPath,
  type Queue,
  QUEUES,
  STATUS_LABEL,
  STATUS_VARIANT,
} from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { SELECT_CLASS } from "../../../settings/form-status";
import { ListToolbar, Pager } from "../../crm/_components/list-controls";
import { param, type SearchParams } from "../../crm/data";

const LINK = "font-medium underline-offset-4 hover:underline";

export default async function ConversationsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = inboxPath(slug, "conversations");
  const workspace = await workspaceWith(slug, "inbox.read", path);
  const search = await searchParams;
  const queueParam = param(search.queue);
  const queue: Queue = QUEUES.some((q) => q.key === queueParam) ? (queueParam as Queue) : "all";
  const statusParam = param(search.status);
  const status =
    statusParam && statusParam in STATUS_LABEL ? (statusParam as ConversationStatus) : undefined;
  const q = param(search.q, 100);
  const cursor = param(search.cursor);
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/conversations", {
        params: { path: { slug }, query: { queue, status, q, cursor } },
      }),
    ),
    path,
  );
  const canWrite = workspace.permissions.includes("inbox.write");
  const queueHref = (key: Queue) => {
    const query = new URLSearchParams({ queue: key });
    if (status) query.set("status", status);
    return `${path}?${query.toString()}`;
  };

  return (
    <section className="flex flex-col gap-4" aria-labelledby="conversations-heading">
      <h2 id="conversations-heading" className="text-lg font-medium">
        Conversations
      </h2>
      <nav aria-label="Queues">
        <ul className="flex gap-2">
          {QUEUES.map((item) => (
            <li key={item.key}>
              <Link
                href={queueHref(item.key)}
                aria-current={queue === item.key ? "page" : undefined}
                className={cn(
                  "rounded-md border px-3 py-1 text-sm",
                  queue === item.key ? "bg-secondary font-medium" : "text-muted-foreground",
                )}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <ListToolbar
        action={path}
        q={q}
        label="Search subject, name or phone/email"
        extra={
          <>
            <input type="hidden" name="queue" value={queue} />
            <div className="flex flex-col gap-1">
              <label htmlFor="status" className="text-sm font-medium">
                Status
              </label>
              <select
                id="status"
                name="status"
                defaultValue={status ?? ""}
                className={cn(SELECT_CLASS, "w-48")}
              >
                <option value="">Any status</option>
                {(Object.keys(STATUS_LABEL) as ConversationStatus[]).map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </div>
          </>
        }
      >
        {canWrite ? (
          <Button asChild>
            <Link href={inboxPath(slug, "conversations", "new")}>New conversation</Link>
          </Button>
        ) : null}
      </ListToolbar>
      {page.items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={
            q || status || queue !== "all" ? "No matching conversations" : "No conversations yet"
          }
          description={
            canWrite && !q ? "Record a phone call or walk-in enquiry to start one." : undefined
          }
        />
      ) : (
        <Table>
          <TableCaption className="sr-only">Conversations</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Subject</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Assigned to</TableHead>
              <TableHead>Channel</TableHead>
              <TableHead>Last message</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <Link className={LINK} href={inboxPath(slug, "conversations", c.id)}>
                      {c.subject}
                    </Link>
                    {c.handler === "assistant" ? <Badge variant="info">Assistant</Badge> : null}
                  </span>
                </TableCell>
                <TableCell>{c.customer_label}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[c.status]}>{STATUS_LABEL[c.status]}</Badge>
                </TableCell>
                <TableCell>{c.assignee?.display_name ?? "Unassigned"}</TableCell>
                <TableCell>{c.channel.name}</TableCell>
                <TableCell>
                  <time dateTime={c.last_message_at}>
                    {formatInZone(c.last_message_at, workspace.timezone)}
                  </time>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Pager
        base={path}
        params={{ queue, status, q }}
        cursor={cursor}
        nextCursor={page.next_cursor}
      />
    </section>
  );
}
