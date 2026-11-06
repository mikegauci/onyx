"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useEffect, useRef } from "react";

import { IDLE } from "@/lib/form-state";
import type { Suppression } from "@/lib/inbox";

import { FormStatus } from "../../../settings/form-status";
import { addSuppression, releaseSuppression } from "../actions";

export function AddSuppressionForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(addSuppression.bind(null, slug), IDLE);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status === "ok") form.current?.reset();
  }, [state]);
  return (
    <form ref={form} action={action} className="flex max-w-md flex-col gap-3" noValidate>
      <FormStatus state={state} />
      <FormField id="suppression-address" label="Email address" error={state.fieldErrors?.address}>
        <Input id="suppression-address" name="address" type="email" required maxLength={320} />
      </FormField>
      <FormField
        id="suppression-note"
        label="Note"
        hint="Why, for the team. Optional."
        error={state.fieldErrors?.note}
      >
        <Input id="suppression-note" name="note" maxLength={500} />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Block address"}
      </Button>
    </form>
  );
}

export function ReleaseSuppression({
  slug,
  suppression,
}: {
  slug: string;
  suppression: Suppression;
}) {
  const [state, action, pending] = useActionState(
    releaseSuppression.bind(null, slug, suppression.id),
    IDLE,
  );
  return (
    <form
      action={action}
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        const ok = window.confirm(
          `Release ${suppression.address}? Onyx will be able to email it again.`,
        );
        if (!ok) e.preventDefault();
      }}
    >
      <FormStatus state={state} />
      <Button
        type="submit"
        variant="outline"
        size="sm"
        disabled={pending}
        className="self-start"
        aria-label={`Release ${suppression.address}`}
      >
        Release
      </Button>
    </form>
  );
}
