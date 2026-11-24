import { PageHeader } from "@onyx/ui/components/page";
import { EmptyState } from "@onyx/ui/components/states";
import { CircleCheck } from "lucide-react";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";
import { taskHref } from "@/lib/tasks";

import { TaskRow } from "./task-row";

type Props = { params: Promise<{ slug: string }> };

/** Work workflows hand to staff. The API decides who sees which task. */
export default async function TasksPage({ params }: Props) {
  const { slug } = await params;
  const path = `/w/${slug}/tasks`;
  const workspace = await workspaceWith(slug, "tasks.read", path);
  const tasks = requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/tasks", { params: { path: { slug } } })),
    path,
  );
  const canCancel = workspace.permissions.includes("tasks.manage");
  return (
    <section aria-labelledby="tasks-heading" className="flex max-w-3xl flex-col gap-8">
      <PageHeader
        id="tasks-heading"
        eyebrow="Workspace"
        title="Tasks"
        description="Things that need a person, such as replies waiting for approval. They close by themselves when the work is done, for example when the reply is approved."
      />
      {tasks.items.length === 0 ? (
        <EmptyState
          icon={CircleCheck}
          title="Nothing waiting for you."
          description="New tasks appear here when a workflow needs a person."
        />
      ) : (
        <ul className="bg-card divide-y rounded-2xl border" aria-label="Open tasks">
          {tasks.items.map((t) => (
            <TaskRow
              key={t.id}
              slug={slug}
              canCancel={canCancel}
              task={{
                id: t.id,
                title: t.title,
                priority: t.priority,
                status: t.status,
                href: taskHref(slug, t),
                due: t.due_at ? formatInZone(t.due_at, workspace.timezone) : null,
              }}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
