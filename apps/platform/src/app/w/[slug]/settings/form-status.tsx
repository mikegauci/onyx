import type { FormState } from "./actions";
import { selectClass } from "@onyx/ui/lib/form-classes";

/** Announces the result of a settings form to screen readers and sighted users. */
export function FormStatus({ state }: { state: FormState }) {
  if (state.status === "idle" || !state.message) return null;
  return (
    <div
      role={state.status === "error" ? "alert" : "status"}
      className={
        state.status === "error"
          ? "border-destructive/40 text-destructive rounded-md border p-3 text-sm"
          : "border-success/40 rounded-md border p-3 text-sm"
      }
    >
      <p>{state.message}</p>
      {state.status === "error" && state.requestId ? (
        <p className="text-muted-foreground mt-1 font-mono text-xs">Reference: {state.requestId}</p>
      ) : null}
    </div>
  );
}

export const SELECT_CLASS = selectClass;
