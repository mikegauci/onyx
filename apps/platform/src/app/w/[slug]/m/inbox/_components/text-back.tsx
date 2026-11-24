"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass, textareaClass } from "@onyx/ui/lib/form-classes";
import type { components } from "@onyx/api-client";
import { PhoneForwarded } from "lucide-react";
import { useActionState, useState } from "react";

import { IDLE } from "@/lib/form-state";
import type { WhatsAppTemplate } from "@/lib/inbox";

import { FormStatus } from "../../../settings/form-status";
import { updatePhoneLine } from "../actions";

type PhoneLine = components["schemas"]["PhoneLineOut"];

const SMS_MAX = 320;

/** Fill {{1}}, {{2}}… with the values, leaving unfilled ones visible. */
function preview(body: string, values: string[]): string {
  return body.replace(/\{\{(\d+)\}\}/g, (match, n: string) => values[Number(n) - 1] || match);
}

export function TextBackForm({
  slug,
  line,
  templates,
}: {
  slug: string;
  line: PhoneLine;
  templates: WhatsAppTemplate[];
}) {
  const [state, action, pending] = useActionState(updatePhoneLine.bind(null, slug, line.id), IDLE);
  const usable = templates.filter((t) => t.usable);
  const [templateId, setTemplateId] = useState(line.template_id ?? "");
  const template = usable.find((t) => t.id === templateId);
  const [values, setValues] = useState<string[]>(line.template_params);
  const [sms, setSms] = useState(line.sms_text ?? "");
  const errors = state.fieldErrors ?? {};
  const count = template?.param_count ?? 0;

  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      <FormStatus state={state} />
      <p className="bg-background/40 flex items-start gap-3 rounded-xl border p-4 text-sm">
        <PhoneForwarded aria-hidden className="text-brand mt-0.5 size-4 shrink-0" />
        <span>
          Ask your phone provider to forward <strong>unanswered and busy</strong> calls to{" "}
          <strong className="font-mono">{line.number}</strong>. Missed calls then appear in the{" "}
          {line.whatsapp_channel.name} inbox with a call-back task.
        </span>
      </p>

      <label className="flex items-center gap-3 text-sm">
        <input
          type="checkbox"
          name="text_back_enabled"
          defaultChecked={line.text_back_enabled}
          className="accent-brand size-4"
        />
        Send the caller a message automatically
      </label>

      <FormField
        id={`template-${line.id}`}
        label="WhatsApp template"
        hint="An approved utility template from this WhatsApp number. Refresh templates above after creating one in WhatsApp Manager."
        error={errors.template_id}
      >
        <select
          id={`template-${line.id}`}
          name="template_id"
          className={selectClass}
          value={templateId}
          onChange={(e) => {
            setTemplateId(e.target.value);
            setValues([]);
          }}
        >
          <option value="">No template</option>
          {usable.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.language})
            </option>
          ))}
        </select>
      </FormField>

      {Array.from({ length: count }, (_, i) => (
        <FormField
          key={`${templateId}-${i}`}
          id={`value-${line.id}-${i}`}
          label={`Value {{${i + 1}}}`}
          error={errors[`template_params.${i}`] ?? (i === 0 ? errors.template_params : undefined)}
        >
          <Input
            id={`value-${line.id}-${i}`}
            name="template_params"
            maxLength={200}
            value={values[i] ?? ""}
            onChange={(e) => {
              const next = [...values];
              next[i] = e.target.value;
              setValues(next);
            }}
          />
        </FormField>
      ))}

      {template?.body ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-muted-foreground text-xs">What the caller receives on WhatsApp</p>
          <p
            aria-label="Template preview"
            className="border-brand/25 bg-brand/[0.07] max-w-md rounded-2xl rounded-tr-md border px-4 py-3 text-sm whitespace-pre-wrap"
          >
            {preview(template.body, values)}
          </p>
        </div>
      ) : null}

      <fieldset className="flex flex-col gap-4 rounded-xl border p-4">
        <legend className="px-1 text-sm font-medium">
          SMS if the caller isn&apos;t on WhatsApp
        </legend>
        <FormField
          id={`sms-${line.id}`}
          label="SMS text"
          hint={`${sms.length}/${SMS_MAX} characters. Leave empty to skip the SMS.`}
          error={errors.sms_text}
        >
          <textarea
            id={`sms-${line.id}`}
            name="sms_text"
            maxLength={SMS_MAX}
            value={sms}
            onChange={(e) => setSms(e.target.value)}
            className={`${textareaClass} min-h-20`}
          />
        </FormField>
        <FormField
          id={`sender-${line.id}`}
          label="Sender name"
          hint="Up to 11 letters or numbers, e.g. your business name. Callers can't reply by SMS."
          error={errors.sms_sender}
        >
          <Input
            id={`sender-${line.id}`}
            name="sms_sender"
            maxLength={11}
            defaultValue={line.sms_sender ?? ""}
            className="sm:w-48"
          />
        </FormField>
      </fieldset>

      <FormField
        id={`cooldown-${line.id}`}
        label="Hours between messages to the same caller"
        error={errors.cooldown_hours}
      >
        <Input
          id={`cooldown-${line.id}`}
          name="cooldown_hours"
          type="number"
          min={1}
          max={168}
          defaultValue={line.cooldown_hours}
          className="w-28"
        />
      </FormField>

      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save text-back settings"}
      </Button>
    </form>
  );
}
