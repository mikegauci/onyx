"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { type FormState, failureState } from "@/lib/form-state";

export async function closeTask(
  slug: string,
  taskId: string,
  how: "complete" | "cancel",
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    how === "complete"
      ? api.POST("/v1/w/{slug}/tasks/{task_id}/complete", {
          params: { path: { slug, task_id: taskId } },
        })
      : api.POST("/v1/w/{slug}/tasks/{task_id}/cancel", {
          params: { path: { slug, task_id: taskId } },
        }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(`/w/${slug}`, "layout");
  return { status: "ok", message: how === "complete" ? "Marked done." : "Task cancelled." };
}
