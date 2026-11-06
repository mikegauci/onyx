"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useEffect, useRef } from "react";

import type { AssistantPolicy } from "@/lib/assistant";
import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { deletePolicy, savePolicy } from "../actions";

const TEXTAREA_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-32 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none aria-invalid:border-destructive";

/** Add a policy (``policy`` absent) or edit one; the topic of an existing policy is fixed. */
export function PolicyForm({ slug, policy }: { slug: string; policy?: AssistantPolicy }) {
  const [state, action, pending] = useActionState(
    savePolicy.bind(null, slug, policy?.topic ?? null),
    IDLE,
  );
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status === "ok" && !policy) form.current?.reset();
  }, [state, policy]);
  const errors = state.fieldErrors ?? {};
  const id = (name: string) => `${policy?.topic ?? "new"}-${name}`;
  return (
    <form ref={form} action={action} className="flex flex-col gap-3" noValidate>
      <FormStatus state={state} />
      {policy ? null : (
        <FormField
          id={id("topic")}
          label="Topic"
          error={errors.topic}
          hint="A short key such as delivery, returns, warranty or lead_times."
        >
          <Input id={id("topic")} name="topic" required maxLength={40} autoComplete="off" />
        </FormField>
      )}
      <FormField id={id("title")} label="Title" error={errors.title}>
        <Input
          id={id("title")}
          name="title"
          required
          maxLength={100}
          defaultValue={policy?.title}
        />
      </FormField>
      <FormField id={id("body")} label="Policy text" error={errors.body}>
        <textarea
          id={id("body")}
          name="body"
          required
          maxLength={4000}
          defaultValue={policy?.body}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : policy ? "Save policy" : "Add policy"}
      </Button>
    </form>
  );
}

export function DeletePolicyForm({ slug, policy }: { slug: string; policy: AssistantPolicy }) {
  const [state, action, pending] = useActionState(
    deletePolicy.bind(null, slug, policy.topic),
    IDLE,
  );
  return (
    <form action={action} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <Button
        type="submit"
        variant="outline"
        size="sm"
        disabled={pending}
        className="self-start"
        aria-label={`Delete policy ${policy.title}`}
      >
        Delete
      </Button>
    </form>
  );
}
