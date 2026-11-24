"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { textareaClass } from "@onyx/ui/lib/form-classes";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { applyImport, type ImportState, previewImport, saveSource } from "../actions";

const TEXTAREA = `${textareaClass} min-h-48 font-mono text-xs`;

export function SourceForm({
  slug,
  baseUrl,
  fieldMap,
}: {
  slug: string;
  baseUrl: string;
  fieldMap: string;
}) {
  const [state, action, pending] = useActionState(saveSource.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex max-w-2xl flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField
        id="base_url"
        label="Website address"
        hint="Your dealership's WordPress site with the Vehica theme, for example https://ventur.com.mt."
        error={state.fieldErrors?.base_url}
      >
        <Input id="base_url" name="base_url" defaultValue={baseUrl} required maxLength={500} />
      </FormField>
      <details>
        <summary className="cursor-pointer text-sm underline">Field map (advanced)</summary>
        <FormField
          id="field_map"
          label="Which Vehica field holds what"
          hint={
            'JSON. Add a rule to mark sold cars, for example "sold": {"field": "vehica_6657", "values": ["Sold"]}.'
          }
          error={state.fieldErrors?.field_map}
        >
          <textarea id="field_map" name="field_map" defaultValue={fieldMap} className={TEXTAREA} />
        </FormField>
      </details>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        {pending ? "Checking…" : "Save website"}
      </Button>
    </form>
  );
}

function Summary({ preview }: { preview: NonNullable<ImportState["preview"]> }) {
  return (
    <div className="bg-card flex flex-col gap-2 rounded-2xl border p-5 text-sm">
      <p>
        {preview.listings} listings on the site: <strong>{preview.create}</strong> new,{" "}
        <strong>{preview.update}</strong> changed, {preview.unchanged} unchanged,{" "}
        <strong>{preview.withdraw}</strong> no longer listed
        {preview.skipped ? `, ${preview.skipped} skipped (not readable)` : ""}.
      </p>
      {preview.sample.length > 0 ? (
        <ul className="text-muted-foreground flex flex-col gap-1 text-xs" aria-label="Changes">
          {preview.sample.map((c) => (
            <li key={`${c.action}-${c.source_ref}`}>
              {c.action === "create"
                ? "New"
                : c.action === "update"
                  ? "Changed"
                  : "No longer listed"}
              : {c.title}
              {c.action === "update" ? ` (${c.fields.join(", ")})` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function ImportControls({ slug }: { slug: string }) {
  const [previewState, preview, previewing] = useActionState<ImportState>(
    previewImport.bind(null, slug),
    IDLE,
  );
  const [applyState, apply, applying] = useActionState<ImportState>(
    applyImport.bind(null, slug),
    IDLE,
  );
  const shown = applyState.preview ?? previewState.preview;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-3">
        <form action={preview}>
          <Button type="submit" variant="outline" disabled={previewing || applying}>
            {previewing ? "Reading the site…" : "Preview import"}
          </Button>
        </form>
        {previewState.preview && !applyState.applied ? (
          <form action={apply}>
            <Button type="submit" disabled={previewing || applying}>
              {applying ? "Importing…" : "Import these changes"}
            </Button>
          </form>
        ) : null}
      </div>
      <FormStatus state={applyState.status !== "idle" ? applyState : previewState} />
      {shown ? <Summary preview={shown} /> : null}
    </div>
  );
}
