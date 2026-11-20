"use client";

import type { components } from "@onyx/api-client";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import Link from "next/link";
import { useActionState, useState } from "react";

import { IDLE } from "@/lib/form-state";
import { slugify } from "@/lib/tenants";

import { FormStatus, SELECT_CLASS } from "../../../w/[slug]/settings/form-status";
import { type AdminFormState, createOrganization } from "../actions";
import { BrandColorField, CopyLink } from "@/components/brand-fields";

type Module = components["schemas"]["ModuleOut"];

/** Every module a selection needs, so the API's dependency check passes. */
function withRequirements(selected: Set<string>, modules: Module[]): Set<string> {
  const all = new Set(selected);
  let added = true;
  while (added) {
    added = false;
    for (const m of modules) {
      if (!all.has(m.key)) continue;
      for (const r of m.requires) {
        if (!all.has(r)) {
          all.add(r);
          added = true;
        }
      }
    }
  }
  return all;
}

export function NewOrganizationForm({
  modules,
  timezones,
}: {
  modules: Module[];
  timezones: string[];
}) {
  const [state, action, pending] = useActionState<AdminFormState, FormData>(
    createOrganization,
    IDLE,
  );
  const errors = state.fieldErrors ?? {};
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set(["crm", "inbox"]));

  if (state.status === "ok" && state.inviteLink && state.slug) {
    return (
      <div className="flex flex-col gap-4">
        <FormStatus state={state} />
        <CopyLink link={state.inviteLink} label="Owner's one-time invitation link" />
        <div className="flex flex-wrap gap-3">
          <Button asChild>
            <Link href={`/admin/organizations/${state.slug}`}>Open the organisation</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/admin">Back to organisations</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="org-name" label="Organisation name" error={errors.name}>
        <Input
          id="org-name"
          name="name"
          required
          maxLength={200}
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (!slugEdited) setSlug(slugify(e.target.value));
          }}
        />
      </FormField>
      <FormField
        id="org-slug"
        label="Address"
        hint="Used in links: /w/your-slug. Lowercase letters, digits and hyphens."
        error={errors.slug}
      >
        <Input
          id="org-slug"
          name="slug"
          required
          maxLength={63}
          value={slug}
          onChange={(e) => {
            setSlug(e.target.value);
            setSlugEdited(true);
          }}
        />
      </FormField>
      <FormField
        id="org-owner"
        label="Owner's email"
        hint="They get a one-time link to join as owner. Onyx shows it here; it is not emailed."
        error={errors.owner_email}
      >
        <Input id="org-owner" name="owner_email" type="email" required autoComplete="off" />
      </FormField>
      <FormField id="org-timezone" label="Timezone" error={errors.timezone}>
        <select
          id="org-timezone"
          name="timezone"
          defaultValue="Europe/Malta"
          className={SELECT_CLASS}
        >
          {timezones.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </FormField>
      <FormField
        id="org-display"
        label="Display name"
        hint="Optional. Shown in the workspace instead of the organisation name."
        error={errors.display_name}
      >
        <Input id="org-display" name="display_name" maxLength={200} />
      </FormField>
      <BrandColorField id="org-color" error={errors.brand_color} />
      <FormField
        id="org-budget"
        label="AI budget per month (USD)"
        hint="Optional. Without a budget the assistant cannot run."
        error={errors.ai_monthly_limit_usd_micros}
      >
        <Input id="org-budget" name="ai_budget" type="number" min={0} step="0.01" />
      </FormField>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Modules</legend>
        {errors.modules ? (
          <p role="alert" className="text-destructive text-sm">
            {state.message}
          </p>
        ) : null}
        {modules.map((m) => (
          <label key={m.key} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              name="modules"
              value={m.key}
              checked={selected.has(m.key)}
              onChange={(e) => {
                const next = new Set(selected);
                if (e.target.checked) next.add(m.key);
                else next.delete(m.key);
                setSelected(e.target.checked ? withRequirements(next, modules) : next);
              }}
            />
            <span>
              <span className="font-medium">{m.name}</span>
              {m.requires.length ? (
                <span className="text-muted-foreground"> · needs {m.requires.join(", ")}</span>
              ) : null}
            </span>
          </label>
        ))}
      </fieldset>
      <p className="text-muted-foreground text-xs">Currency: EUR (the only currency for now).</p>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Creating…" : "Create organisation"}
      </Button>
    </form>
  );
}
