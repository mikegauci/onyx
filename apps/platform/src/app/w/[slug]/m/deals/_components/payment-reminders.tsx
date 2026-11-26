"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass, textareaClass } from "@onyx/ui/lib/form-classes";
import Link from "next/link";
import { useActionState, useState } from "react";

import { euros } from "@/lib/automotive";
import { crmPath } from "@/lib/crm";
import { dealsPath } from "@/lib/deals";
import { IDLE } from "@/lib/form-state";
import { formatDay } from "@/lib/reminders";
import {
  PAYMENT_PARAM_LABEL,
  PAYMENT_REMINDER_KINDS,
  PAYMENT_REMINDER_LABEL,
  type PaymentReminder,
  type PaymentReminderKind,
  type PaymentReminderSettings,
  paymentSkipReason,
} from "@/lib/schedules";

import { FormStatus } from "../../../settings/form-status";
import {
  dismissPaymentReminder,
  savePaymentReminderSettings,
  sendPaymentReminders,
} from "../schedule-actions";

const STATUS_LABEL: Record<string, string> = {
  pending: "To send",
  sent: "Sent",
  dismissed: "Dismissed",
  skipped: "Not sent",
};
const STATUS_VARIANT: Record<string, "success" | "warning" | "outline" | "secondary"> = {
  pending: "warning",
  sent: "success",
  dismissed: "outline",
  skipped: "secondary",
};

function Dismiss({ slug, id }: { slug: string; id: string }) {
  const [, action, pending] = useActionState(dismissPaymentReminder.bind(null, slug, id), IDLE);
  return (
    <form action={action}>
      <Button type="submit" variant="ghost" size="sm" disabled={pending}>
        Dismiss
      </Button>
    </form>
  );
}

export function PaymentReminderList({
  slug,
  items,
  canSend,
  canWrite,
}: {
  slug: string;
  items: PaymentReminder[];
  canSend: boolean;
  canWrite: boolean;
}) {
  const [state, action, pending] = useActionState(sendPaymentReminders.bind(null, slug), IDLE);
  const sendable = (r: PaymentReminder) => r.status === "pending" || r.status === "skipped";
  const formId = "send-payment-reminders";
  return (
    <div className="flex flex-col gap-3">
      <FormStatus state={state} />
      <form id={formId} action={action} className="contents" />
      <ul className="divide-y rounded-2xl border" aria-label="Payment reminders">
        {items.map((r) => (
          <li key={r.id} className="flex flex-wrap items-start gap-3 p-4">
            {canSend && sendable(r) ? (
              <input
                type="checkbox"
                name="reminder_id"
                value={r.id}
                form={formId}
                defaultChecked={r.status === "pending"}
                aria-label={`Send to ${r.contact_name}`}
                className="mt-1"
              />
            ) : null}
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant={r.kind === "overdue" ? "destructive" : "secondary"}>
                  {PAYMENT_REMINDER_LABEL[r.kind]}
                </Badge>
                <Link
                  href={crmPath(slug, "contacts", r.contact_id)}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {r.contact_name}
                </Link>
                <Link
                  href={dealsPath(slug, "finance", "schedules", r.schedule_id)}
                  className="text-muted-foreground underline-offset-4 hover:underline"
                >
                  {r.label}
                </Link>
                <Badge variant={STATUS_VARIANT[r.status] ?? "outline"}>
                  {STATUS_LABEL[r.status] ?? r.status}
                </Badge>
              </p>
              <p className="text-muted-foreground text-xs">
                Installment {r.installment_number} · due {formatDay(r.due_on)} ·{" "}
                {r.owed_cents > 0 ? `${euros(r.owed_cents)} owed` : "paid"}
                {r.channel ? ` · sent by ${r.channel === "email" ? "email" : "WhatsApp"}` : null}
                {!r.has_phone && !r.has_email ? " · no phone or email" : null}
              </p>
              {paymentSkipReason(r.skip_reason) ? (
                <p className="text-xs">{paymentSkipReason(r.skip_reason)}</p>
              ) : null}
            </div>
            {canWrite && sendable(r) ? <Dismiss slug={slug} id={r.id} /> : null}
          </li>
        ))}
      </ul>
      {canSend && items.some(sendable) ? (
        <Button type="submit" form={formId} disabled={pending} className="self-start">
          {pending ? "Sending…" : "Send selected reminders"}
        </Button>
      ) : null}
    </div>
  );
}

type TemplateOption = { id: string; label: string; paramCount: number; body: string | null };

function KindFields({
  kind,
  settings,
  templates,
}: {
  kind: PaymentReminderKind;
  settings: PaymentReminderSettings;
  templates: TemplateOption[];
}) {
  const current = settings[kind];
  const [templateId, setTemplateId] = useState(current.template_id ?? "");
  const chosen = templates.find((t) => t.id === templateId);
  return (
    <fieldset className="flex flex-col gap-3 rounded-xl border p-4">
      <legend className="px-1 text-sm font-medium">{PAYMENT_REMINDER_LABEL[kind]}</legend>
      <FormField
        id={`${kind}_days`}
        label={kind === "before_due" ? "Days before the due date" : "Days after the due date"}
      >
        <Input
          id={`${kind}_days`}
          name={`${kind}_days`}
          type="number"
          min={1}
          max={kind === "before_due" ? 30 : 60}
          defaultValue={current.days}
          className="w-28"
        />
      </FormField>
      <FormField
        id={`${kind}_message`}
        label="Message"
        hint="Email, and WhatsApp within 24 hours of their last message. {name}, {car}, {amount} and {due} are filled in."
      >
        <textarea
          id={`${kind}_message`}
          name={`${kind}_message`}
          maxLength={1000}
          defaultValue={current.message}
          className={`${textareaClass} min-h-20`}
        />
      </FormField>
      <FormField id={`${kind}_template_id`} label="WhatsApp template (after 24 hours)">
        <select
          id={`${kind}_template_id`}
          name={`${kind}_template_id`}
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          className={selectClass}
        >
          <option value="">None (use email)</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </FormField>
      {chosen?.body ? (
        <p className="bg-muted rounded-xl px-4 py-3 text-sm whitespace-pre-wrap">{chosen.body}</p>
      ) : null}
      {chosen
        ? Array.from({ length: chosen.paramCount }, (_, i) => (
            <FormField key={i} id={`${kind}-param-${i}`} label={`Value {{${i + 1}}}`}>
              <select
                id={`${kind}-param-${i}`}
                name={`${kind}_param`}
                defaultValue={current.params[i] ?? settings.param_keys[i] ?? "first_name"}
                className={selectClass}
              >
                {settings.param_keys.map((k) => (
                  <option key={k} value={k}>
                    {PAYMENT_PARAM_LABEL[k] ?? k}
                  </option>
                ))}
              </select>
            </FormField>
          ))
        : null}
    </fieldset>
  );
}

export function PaymentReminderSettingsForm({
  slug,
  settings,
  templates,
}: {
  slug: string;
  settings: PaymentReminderSettings;
  templates: TemplateOption[];
}) {
  const [state, action, pending] = useActionState(
    savePaymentReminderSettings.bind(null, slug),
    IDLE,
  );
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4">
      <FormStatus state={state} />
      {PAYMENT_REMINDER_KINDS.map((kind) => (
        <KindFields key={kind} kind={kind} settings={settings} templates={templates} />
      ))}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
