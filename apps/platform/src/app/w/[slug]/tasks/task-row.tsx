"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import Link from "next/link";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../settings/form-status";
import { closeTask } from "./actions";

export type TaskView = {
  id: string;
  title: string;
  priority: "normal" | "urgent";
  status: "open" | "done" | "cancelled";
  href: string | null;
  due: string | null;
};

export function TaskRow({
  slug,
  task,
  canCancel,
}: {
  slug: string;
  task: TaskView;
  canCancel: boolean;
}) {
  const [doneState, complete, completing] = useActionState(
    closeTask.bind(null, slug, task.id, "complete"),
    IDLE,
  );
  const [cancelState, cancel, cancelling] = useActionState(
    closeTask.bind(null, slug, task.id, "cancel"),
    IDLE,
  );
  const busy = completing || cancelling;
  return (
    <li className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center">
      <div className="flex flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          {task.priority === "urgent" ? <Badge variant="destructive">Urgent</Badge> : null}
          {task.href ? (
            <Link className="font-medium underline" href={task.href}>
              {task.title}
            </Link>
          ) : (
            <span className="font-medium">{task.title}</span>
          )}
        </span>
        {task.due ? <span className="text-muted-foreground text-xs">Due {task.due}</span> : null}
        <FormStatus state={doneState} />
        <FormStatus state={cancelState} />
      </div>
      {task.status === "open" ? (
        <div className="flex gap-2">
          <form action={complete}>
            <Button type="submit" size="sm" disabled={busy} aria-label={`Mark done: ${task.title}`}>
              Done
            </Button>
          </form>
          {canCancel ? (
            <form action={cancel}>
              <Button
                type="submit"
                size="sm"
                variant="outline"
                disabled={busy}
                aria-label={`Cancel: ${task.title}`}
              >
                Cancel
              </Button>
            </form>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
