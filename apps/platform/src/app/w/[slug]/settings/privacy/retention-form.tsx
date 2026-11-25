"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { useActionState } from "react";

import { type FormState, saveRetention } from "../actions";
import { FormStatus, SELECT_CLASS } from "../form-status";

const INITIAL: FormState = { status: "idle" };

export function RetentionForm({
  slug,
  months,
  choices,
}: {
  slug: string;
  months: number | null;
  choices: number[];
}) {
  const [state, action, pending] = useActionState(saveRetention.bind(null, slug), INITIAL);
  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField
        id="retention-months"
        label="Remove conversations after"
        hint="Counted from the last message."
        error={state.fieldErrors?.conversation_retention_months}
        className="max-w-xs"
      >
        <select
          id="retention-months"
          name="months"
          defaultValue={months === null ? "" : String(months)}
          className={SELECT_CLASS}
        >
          <option value="">Keep everything</option>
          {choices.map((m) => (
            <option key={m} value={m}>
              {m < 12 ? `${m} months` : `${m / 12} year${m === 12 ? "" : "s"}`} without activity
            </option>
          ))}
        </select>
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
