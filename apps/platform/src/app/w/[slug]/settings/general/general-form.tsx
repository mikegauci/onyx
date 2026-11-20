"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState } from "react";

import { BrandColorField } from "@/components/brand-fields";
import { type FormState, updateWorkspace } from "../actions";
import { FormStatus, SELECT_CLASS } from "../form-status";

type Props = {
  slug: string;
  name: string;
  timezone: string;
  timezones: string[];
  displayName: string;
  brandColor: string;
  currency: string;
};

const INITIAL: FormState = { status: "idle" };

export function GeneralForm({
  slug,
  name,
  timezone,
  timezones,
  displayName,
  brandColor,
  currency,
}: Props) {
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
      <FormField
        id="display_name"
        label="Display name"
        hint="Optional. Shown in the workspace instead of the name. Empty uses the name."
        error={state.fieldErrors?.display_name}
      >
        <Input id="display_name" name="display_name" defaultValue={displayName} maxLength={200} />
      </FormField>
      <BrandColorField
        id="brand_color"
        error={state.fieldErrors?.brand_color}
        defaultValue={brandColor}
      />
      <FormField
        id="currency"
        label="Currency"
        hint="Prices, VAT and quotes are in euro. Other currencies are not supported yet."
      >
        <Input id="currency" value={currency} readOnly className="w-24" />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}
