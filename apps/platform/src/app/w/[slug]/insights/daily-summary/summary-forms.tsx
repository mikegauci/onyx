"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass } from "@onyx/ui/lib/form-classes";
import { useActionState, useState } from "react";

import {
  MAX_RECIPIENTS,
  PARAM_KEYS,
  PARAM_LABEL,
  type SummarySettings,
  timeValue,
} from "@/lib/daily-summary";
import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../settings/form-status";
import { saveSummarySettings, sendTestSummary } from "./actions";

export type TemplateOption = { id: string; label: string; paramCount: number; body: string | null };

export function SummarySettingsForm({
  slug,
  settings,
  templates,
}: {
  slug: string;
  settings: SummarySettings;
  templates: TemplateOption[];
}) {
  const [state, action, pending] = useActionState(saveSummarySettings.bind(null, slug), IDLE);
  const saved = new Map(settings.recipients.map((r) => [r.user_id, r]));
  const [chosen, setChosen] = useState<Set<string>>(new Set(saved.keys()));
  const [templateId, setTemplateId] = useState(settings.template_id ?? "");
  const template = templates.find((t) => t.id === templateId);
  const toggle = (id: string, on: boolean) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <form action={action} className="flex max-w-2xl flex-col gap-5">
      <FormStatus state={state} />
      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          name="enabled"
          defaultChecked={settings.enabled}
          className="accent-brand mt-0.5 size-4"
        />
        <span>Send the daily summary</span>
      </label>
      <FormField
        id="send_at"
        label="Send at"
        hint={`Every day at this time (${settings.timezone}). It covers that day up to then.`}
      >
        <Input
          id="send_at"
          name="send_at"
          type="time"
          step={60}
          defaultValue={timeValue(settings.send_at)}
          className="w-36"
        />
      </FormField>

      <fieldset className="flex flex-col gap-3 rounded-xl border p-4">
        <legend className="px-1 text-sm font-medium">Who gets it (up to {MAX_RECIPIENTS})</legend>
        {settings.members.map((m) => {
          const current = saved.get(m.user_id);
          const on = chosen.has(m.user_id);
          const error = state.fieldErrors?.[`whatsapp_${m.user_id}`];
          return (
            <div key={m.user_id} className="flex flex-col gap-2 border-b pb-3 last:border-b-0">
              <label className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  name="recipient"
                  value={m.user_id}
                  checked={on}
                  disabled={!on && chosen.size >= MAX_RECIPIENTS}
                  onChange={(e) => toggle(m.user_id, e.target.checked)}
                  className="accent-brand size-4"
                />
                <span>
                  {m.display_name} <span className="text-muted-foreground">· {m.email}</span>
                </span>
              </label>
              {on ? (
                <div className="flex flex-wrap items-end gap-4 pl-7">
                  <label className="flex items-center gap-2 pb-2 text-sm">
                    <input
                      type="checkbox"
                      name={`email_${m.user_id}`}
                      defaultChecked={current ? current.email : true}
                      className="accent-brand size-4"
                    />
                    By email
                  </label>
                  <FormField
                    id={`whatsapp_${m.user_id}`}
                    label="WhatsApp number (optional)"
                    error={error}
                  >
                    <Input
                      id={`whatsapp_${m.user_id}`}
                      name={`whatsapp_${m.user_id}`}
                      type="tel"
                      inputMode="tel"
                      placeholder="+356 7900 0001"
                      defaultValue={current?.whatsapp ?? ""}
                      className="w-52"
                    />
                  </FormField>
                </div>
              ) : null}
            </div>
          );
        })}
      </fieldset>

      <FormField
        id="template_id"
        label="WhatsApp template"
        hint="WhatsApp only sends an approved utility template to someone who has not written in the last 24 hours. Without one, the summary goes by email only."
      >
        <select
          id="template_id"
          name="template_id"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          className={selectClass}
        >
          <option value="">None (email only)</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </FormField>
      {template?.body ? (
        <p className="bg-muted rounded-xl px-4 py-3 text-sm whitespace-pre-wrap">{template.body}</p>
      ) : null}
      {template
        ? Array.from({ length: template.paramCount }, (_, i) => (
            <FormField key={i} id={`param-${i}`} label={`Value {{${i + 1}}}`}>
              <select
                id={`param-${i}`}
                name="param"
                defaultValue={
                  settings.params[i] ?? (i === template.paramCount - 1 ? "summary" : "workspace")
                }
                className={selectClass}
              >
                {PARAM_KEYS.map((k) => (
                  <option key={k} value={k}>
                    {PARAM_LABEL[k]}
                  </option>
                ))}
              </select>
            </FormField>
          ))
        : null}
      {settings.template_id && !settings.template_ready ? (
        <p className="text-destructive text-sm">
          The saved template can no longer be used. Choose another one.
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}

export function TestButton({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(sendTestSummary.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex flex-col gap-3">
      <FormStatus state={state} />
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        {pending ? "Sending…" : "Send me a test"}
      </Button>
    </form>
  );
}
