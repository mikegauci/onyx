"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass } from "@onyx/ui/lib/form-classes";
import { useActionState, useState } from "react";

import type { DealSettings } from "@/lib/deals";
import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { saveSettings } from "../actions";

const WHEN_LABEL = {
  always: "Every deal",
  financed: "Financed deals",
  trade_in: "Deals with a trade-in",
  deposit: "Once a deposit is recorded",
} as const;

type Row = DealSettings["checklist"][number];

export function DealSettingsForm({ slug, settings }: { slug: string; settings: DealSettings }) {
  const [state, action, pending] = useActionState(saveSettings.bind(null, slug), IDLE);
  const [rows, setRows] = useState<Row[]>(settings.checklist);
  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      <FormStatus state={state} />
      <ol className="flex flex-col gap-3" aria-label="Checklist items">
        {rows.map((row, i) => (
          <li
            key={`${row.key}-${i}`}
            className="bg-background/40 grid gap-3 rounded-xl border p-3 md:grid-cols-[1fr_12rem_auto_auto]"
          >
            <input type="hidden" name="item_key" value={row.key} />
            <FormField id={`label-${i}`} label="Document">
              <Input id={`label-${i}`} name="item_label" defaultValue={row.label} maxLength={100} />
            </FormField>
            <FormField id={`when-${i}`} label="Only when">
              <select
                id={`when-${i}`}
                name="item_when"
                defaultValue={row.when}
                className={selectClass}
              >
                {Object.entries(WHEN_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </FormField>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input
                type="checkbox"
                name="item_required"
                value={String(i)}
                defaultChecked={row.required}
                className="accent-brand size-4"
              />
              Required
            </label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="self-end"
              onClick={() => setRows(rows.filter((_, j) => j !== i))}
            >
              Remove<span className="sr-only"> {row.label}</span>
            </Button>
            <div className="md:col-span-4">
              <FormField id={`note-${i}`} label="Note for the customer (optional)">
                <Input
                  id={`note-${i}`}
                  name="item_note"
                  defaultValue={row.note ?? ""}
                  maxLength={300}
                />
              </FormField>
            </div>
          </li>
        ))}
      </ol>
      <Button
        type="button"
        variant="secondary"
        className="self-start"
        onClick={() =>
          setRows([...rows, { key: "", label: "", required: true, note: null, when: "always" }])
        }
      >
        Add a document
      </Button>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="retention"
          label="Delete document files after (days)"
          hint="Counted from when a deal is collected or cancelled. The deal record stays. 30–3650."
          error={state.fieldErrors?.retention_days}
        >
          <Input
            id="retention"
            name="retention_days"
            inputMode="numeric"
            defaultValue={settings.retention_days}
            className="max-w-32"
          />
        </FormField>
      </div>
      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          name="customer_reminders"
          defaultChecked={settings.customer_reminders}
          className="accent-brand mt-0.5 size-4"
        />
        <span>
          Remind customers about missing documents automatically (at most three reminders).
          <span className="text-muted-foreground block">
            Reminders start once the customer upload link and the scheduler are live.
          </span>
        </span>
      </label>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save settings"}
      </Button>
    </form>
  );
}
