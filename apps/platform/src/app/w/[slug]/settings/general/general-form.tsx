"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState } from "react";

import { type FormState, updateWorkspace } from "../actions";
import { FormStatus, SELECT_CLASS } from "../form-status";

type Props = { slug: string; name: string; timezone: string; timezones: string[] };

const INITIAL: FormState = { status: "idle" };

export function GeneralForm({ slug, name, timezone, timezones }: Props) {
  const [state, action, pending] = useActionState(updateWorkspace.bind(null, slug), INITIAL);
  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="name" label="Workspace name" error={state.fieldErrors?.name}>
        <Input id="name" name="name" defaultValue={name} required maxLength={200} />
      </FormField>
      <FormField
        id="timezone"
        label="Timezone"
        hint="Dates and times are shown in this timezone."
        error={state.fieldErrors?.timezone}
      >
        <select id="timezone" name="timezone" defaultValue={timezone} className={SELECT_CLASS}>
          {timezones.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}
