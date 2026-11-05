"use client";

import { Button } from "@onyx/ui/components/button";
import { ErrorState } from "@onyx/ui/components/states";
import { useActionState } from "react";

import { type AcceptState, acceptInvitation } from "./actions";

export function AcceptForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState<AcceptState, FormData>(acceptInvitation, {});
  if (!token) {
    return (
      <ErrorState
        title="Invitation link is incomplete"
        description="Open the full link you were sent."
      />
    );
  }
  return (
    <form action={action} className="flex flex-col gap-4">
      {state.error ? (
        <ErrorState
          title="Could not accept"
          description={state.error}
          requestId={state.requestId}
        />
      ) : null}
      <input type="hidden" name="token" value={token} />
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Joining…" : "Accept invitation"}
      </Button>
    </form>
  );
}
