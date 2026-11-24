"use client";

import type { components } from "@onyx/api-client";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState } from "react";

import { type FormState, setManualMode, updateControls } from "../actions";
import { FormStatus } from "../form-status";

type Controls = components["schemas"]["ControlsOut"];

const INITIAL: FormState = { status: "idle" };

export function ManualModeForm({
  slug,
  on,
  reason,
}: {
  slug: string;
  on: boolean;
  reason: string | null;
}) {
  const [state, action, pending] = useActionState(setManualMode.bind(null, slug, !on), INITIAL);
  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <p className="text-sm" role="status">
        Manual mode is{" "}
        <strong className={on ? "text-warning font-medium" : "font-medium"}>
          {on ? "on" : "off"}
        </strong>
        {on && reason ? <span className="text-muted-foreground"> · {reason}</span> : null}.
      </p>
      {on ? null : (
        <FormField
          id="manual-reason"
          label="Reason (optional)"
          hint="Shown to everyone in the banner, e.g. “Checking a wrong reply”."
          error={state.fieldErrors?.manual_mode_reason}
        >
          <Input id="manual-reason" name="reason" maxLength={200} />
        </FormField>
      )}
      <Button
        type="submit"
        variant={on ? "default" : "destructive"}
        disabled={pending}
        className="self-start"
      >
        {pending ? "Saving…" : on ? "Turn off manual mode" : "Turn on manual mode"}
      </Button>
    </form>
  );
}

export function SwitchesForm({
  slug,
  controls,
  hasAssistant,
  hasInbox,
}: {
  slug: string;
  controls: Controls;
  hasAssistant: boolean;
  hasInbox: boolean;
}) {
  const [state, action, pending] = useActionState(updateControls.bind(null, slug), INITIAL);
  const overridden = controls.manual_mode ? " (paused by manual mode)" : "";
  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      <FormStatus state={state} />
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-medium">Features</legend>
        <Switch
          name="assistant_enabled"
          checked={controls.assistant_enabled}
          label="Sales assistant"
          hint={
            hasAssistant
              ? `Staff can ask the assistant to draft replies and quotes.${overridden}`
              : "Not on this workspace's plan."
          }
        />
        <Switch
          name="text_back_enabled"
          checked={controls.text_back_enabled}
          label="Missed-call text-back"
          hint={
            hasInbox
              ? `Callers get an automatic message after a missed call. Calls are still logged with a task when it is paused.${overridden}`
              : "Needs the inbox."
          }
        />
      </fieldset>
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-sm font-medium">Before Onyx (baseline)</legend>
        <p className="text-muted-foreground -mt-2 text-sm">
          Optional figures from before the pilot. Insights shows them next to today’s numbers.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            id="baseline_first_reply_minutes"
            label="Typical first reply (minutes)"
            hint="E.g. 120 for about two hours."
            error={state.fieldErrors?.baseline_first_reply_minutes}
          >
            <Input
              id="baseline_first_reply_minutes"
              name="baseline_first_reply_minutes"
              inputMode="numeric"
              defaultValue={controls.baseline_first_reply_minutes ?? ""}
            />
          </FormField>
          <FormField
            id="baseline_enquiries_per_week"
            label="Enquiries per week"
            error={state.fieldErrors?.baseline_enquiries_per_week}
          >
            <Input
              id="baseline_enquiries_per_week"
              name="baseline_enquiries_per_week"
              inputMode="numeric"
              defaultValue={controls.baseline_enquiries_per_week ?? ""}
            />
          </FormField>
        </div>
      </fieldset>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}

function Switch({
  name,
  checked,
  label,
  hint,
}: {
  name: string;
  checked: boolean;
  label: string;
  hint: string;
}) {
  const hintId = `${name}-hint`;
  return (
    <label className="flex items-start gap-3 text-sm">
      <input
        type="checkbox"
        name={name}
        defaultChecked={checked}
        aria-describedby={hintId}
        className="accent-brand mt-0.5 size-4"
      />
      <span className="flex flex-col gap-0.5">
        <span className="font-medium">{label}</span>
        <span id={hintId} className="text-muted-foreground">
          {hint}
        </span>
      </span>
    </label>
  );
}
