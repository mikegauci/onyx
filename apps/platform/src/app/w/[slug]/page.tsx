import { Badge } from "@onyx/ui/components/badge";
import { PageHeader, Panel } from "@onyx/ui/components/page";
import { EmptyState } from "@onyx/ui/components/states";
import {
  ArrowUpRight,
  Blocks,
  Bot,
  Car,
  CircleCheck,
  Contact,
  FileText,
  Handshake,
  Inbox,
  type LucideIcon,
  Library,
  Package,
  Send,
  ShoppingCart,
} from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { MODULES, moduleLabel } from "@/lib/modules";
import { taskHref } from "@/lib/tasks";

type Props = { params: Promise<{ slug: string }> };

const MODULE_ICONS: Record<string, LucideIcon> = {
  crm: Contact,
  catalogue: Package,
  inbox: Inbox,
  quotations: FileText,
  orders: ShoppingCart,
  assistant: Bot,
  outbound: Send,
  knowledge: Library,
  automotive: Car,
  deals: Handshake,
};

const FOCUS = "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none";

export default async function WorkspaceOverviewPage({ params }: Props) {
  const { slug } = await params;
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}`);
  const base = `/w/${workspace.slug}`;
  // The open tasks are a convenience here; a failure just hides the panel.
  const tasks = workspace.permissions.includes("tasks.read")
    ? await withApi((api) => api.GET("/v1/w/{slug}/tasks", { params: { path: { slug } } }))
    : null;
  const openTasks = tasks?.ok ? tasks.data.items.slice(0, 5) : null;

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title={workspace.name}
        description={
          <>
            Signed in as <span className="text-foreground capitalize">{workspace.role}</span> ·
            Times shown in {workspace.timezone}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-labelledby="modules-heading" className="flex flex-col gap-4">
          <h2
            id="modules-heading"
            className="text-muted-foreground font-mono text-[11px] tracking-[0.2em] uppercase"
          >
            Enabled modules
          </h2>
          {workspace.modules.length === 0 ? (
            <EmptyState
              icon={Blocks}
              title="No modules enabled yet"
              description="An administrator can enable modules for this workspace."
            />
          ) : (
            <ul className="bg-border grid gap-px overflow-hidden rounded-2xl border sm:grid-cols-2">
              {workspace.modules.map((key) => {
                const Icon = MODULE_ICONS[key] ?? Blocks;
                return (
                  <li key={key} className="bg-card">
                    <Link
                      href={`${base}/m/${key}`}
                      className={`group hover:bg-foreground/[0.03] flex h-full items-start gap-4 p-5 transition-colors ${FOCUS}`}
                    >
                      <span className="bg-brand/10 text-brand flex size-10 shrink-0 items-center justify-center rounded-xl">
                        <Icon aria-hidden className="size-5" />
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="font-medium">{moduleLabel(key)}</span>
                        <span className="text-muted-foreground text-sm">
                          {MODULES[key]?.blurb ?? `Open ${moduleLabel(key)}`}
                        </span>
                      </span>
                      <ArrowUpRight
                        aria-hidden
                        className="text-muted-foreground group-hover:text-brand size-4 shrink-0 transition-[color,transform] group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                      />
                    </Link>
                  </li>
                );
              })}
              {workspace.modules.length % 2 === 1 ? (
                <li aria-hidden className="bg-card hidden sm:block" />
              ) : null}
            </ul>
          )}
        </section>

        {openTasks ? (
          <Panel
            title="Needs your attention"
            actions={
              <Link
                href={`${base}/tasks`}
                className={`text-muted-foreground hover:text-foreground rounded-sm text-xs ${FOCUS}`}
              >
                All tasks
              </Link>
            }
            flush
            className="self-start"
          >
            {openTasks.length === 0 ? (
              <p className="text-muted-foreground flex items-center gap-2 p-5 text-sm">
                <CircleCheck aria-hidden className="text-success size-4" />
                Nothing waiting for you.
              </p>
            ) : (
              <ul className="divide-y">
                {openTasks.map((task) => {
                  const href = taskHref(slug, task);
                  const body = (
                    <>
                      <span className="min-w-0 flex-1 truncate text-sm">{task.title}</span>
                      {task.due_at ? (
                        <span className="text-muted-foreground shrink-0 text-xs">
                          {formatInZone(task.due_at, workspace.timezone)}
                        </span>
                      ) : task.priority === "urgent" ? (
                        <Badge variant="warning">Urgent</Badge>
                      ) : null}
                    </>
                  );
                  return (
                    <li key={task.id}>
                      {href ? (
                        <Link
                          href={href}
                          className={`hover:bg-foreground/[0.03] flex items-center gap-3 px-5 py-3 transition-colors ${FOCUS}`}
                        >
                          {body}
                        </Link>
                      ) : (
                        <div className="flex items-center gap-3 px-5 py-3">{body}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        ) : null}
      </div>
    </>
  );
}
