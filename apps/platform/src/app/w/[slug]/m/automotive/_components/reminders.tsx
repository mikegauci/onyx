"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass, textareaClass } from "@onyx/ui/lib/form-classes";
import Link from "next/link";
import { useActionState, useState } from "react";

import { crmPath } from "@/lib/crm";
import { IDLE } from "@/lib/form-state";
import {
  type CustomerCar,
  formatDay,
  REMINDER_KIND_LABEL,
  REMINDER_KINDS,
  REMINDER_PARAM_LABEL,
  REMINDER_STATUS_LABEL,
  type Reminder,
  type ReminderKind,
  type ReminderSettings,
  type ReminderStatus,
  reminderSkipReason,
} from "@/lib/reminders";

import { FormStatus } from "../../../settings/form-status";
import {
  dismissReminder,
  recordService,
  saveCustomerCar,
  saveReminderSettings,
  sendReminders,
} from "../reminder-actions";

const STATUS_VARIANT: Record<ReminderStatus, "success" | "warning" | "outline" | "secondary"> = {
  pending: "warning",
  sent: "success",
  dismissed: "outline",
  skipped: "secondary",
};

// --- customer cars (contact page) -------------------------------------------------------------

function CarForm({
  slug,
  contactId,
  car,
  onDone,
}: {
  slug: string;
  contactId: string;
  car: CustomerCar | null;
  onDone?: () => void;
}) {
  const [state, action, pending] = useActionState(
    async (prev: Parameters<typeof saveCustomerCar>[3], data: FormData) => {
      const next = await saveCustomerCar(slug, contactId, car?.id ?? null, prev, data);
      if (next.status === "ok") onDone?.();
      return next;
    },
    IDLE,
  );
  const id = (name: string) => `${car?.id ?? "new"}-${name}`;
  return (
    <form action={action} className="flex flex-col gap-3" aria-label={car ? "Edit car" : "Add car"}>
      <FormStatus state={state} />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id={id("description")} label="Car" error={state.fieldErrors?.description}>
          <Input
            id={id("description")}
            name="description"
            maxLength={200}
            defaultValue={car?.description ?? ""}
            placeholder="Volkswagen Golf 2019"
          />
        </FormField>
        <FormField
          id={id("registration")}
          label="Registration"
          error={state.fieldErrors?.registration}
        >
          <Input
            id={id("registration")}
            name="registration"
            maxLength={16}
            defaultValue={car?.registration ?? ""}
          />
        </FormField>
        <FormField id={id("licence_due_on")} label="Road licence due">
          <Input
            id={id("licence_due_on")}
            name="licence_due_on"
            type="date"
            defaultValue={car?.licence_due_on ?? ""}
          />
        </FormField>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            name="dealer_handles_licence"
            defaultChecked={car?.dealer_handles_licence ?? false}
          />
          We renew the licence for them
        </label>
        <FormField id={id("insurance_due_on")} label="Insurance due">
          <Input
            id={id("insurance_due_on")}
            name="insurance_due_on"
            type="date"
            defaultValue={car?.insurance_due_on ?? ""}
          />
        </FormField>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            name="dealer_handles_insurance"
            defaultChecked={car?.dealer_handles_insurance ?? false}
          />
          We arrange their insurance
        </label>
        <FormField id={id("last_service_on")} label="Last service">
          <Input
            id={id("last_service_on")}
            name="last_service_on"
            type="date"
            defaultValue={car?.last_service_on ?? ""}
          />
        </FormField>
        <FormField id={id("service_interval_months")} label="Service every (months)">
          <Input
            id={id("service_interval_months")}
            name="service_interval_months"
            type="number"
            min={1}
            max={60}
            defaultValue={car?.service_interval_months ?? 12}
            className="w-28"
          />
        </FormField>
        <FormField id={id("collected_on")} label="Collected on">
          <Input
            id={id("collected_on")}
            name="collected_on"
            type="date"
            defaultValue={car?.collected_on ?? ""}
          />
        </FormField>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            name="reminders_paused"
            defaultChecked={car?.reminders_paused ?? false}
          />
          Pause reminders for this car
        </label>
      </div>
      <Button type="submit" disabled={pending} className="self-start" size="sm">
        {pending ? "Saving…" : car ? "Save car" : "Add car"}
      </Button>
    </form>
  );
}

function ServiceForm({ slug, carId }: { slug: string; carId: string }) {
  const [state, action, pending] = useActionState(recordService.bind(null, slug, carId), IDLE);
  return (
    <form action={action} className="flex flex-wrap items-end gap-2" aria-label="Record a service">
      <FormStatus state={state} />
      <FormField id={`${carId}-serviced_on`} label="Serviced on">
        <Input id={`${carId}-serviced_on`} name="serviced_on" type="date" className="w-44" />
      </FormField>
      <Button type="submit" variant="outline" size="sm" disabled={pending}>
        {pending ? "Saving…" : "Record service"}
      </Button>
    </form>
  );
}

function nextLine(car: CustomerCar): string {
  const parts = [`Service ${formatDay(car.next_service_on)}`];
  if (car.next_licence_on) parts.push(`licence ${formatDay(car.next_licence_on)}`);
  if (car.next_insurance_on) parts.push(`insurance ${formatDay(car.next_insurance_on)}`);
  return parts.join(" · ");
}

export function CarsPanel({
  slug,
  contactId,
  cars,
  canWrite,
}: {
  slug: string;
  contactId: string;
  cars: CustomerCar[];
  canWrite: boolean;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">
        Cars this customer owns. Licence and insurance reminders appear only when you handle them
        for the customer; service reminders follow the interval.
      </p>
      {cars.length === 0 ? <p className="text-sm">No cars yet.</p> : null}
      <ul className="flex flex-col gap-3" aria-label="Customer cars">
        {cars.map((car) => (
          <li key={car.id} className="flex flex-col gap-3 rounded-xl border p-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{car.description}</span>
              {car.registration ? (
                <span className="text-muted-foreground font-mono text-xs">{car.registration}</span>
              ) : null}
              {car.reminders_paused ? <Badge variant="outline">Reminders paused</Badge> : null}
              {canWrite ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  onClick={() => setEditing(editing === car.id ? null : car.id)}
                >
                  {editing === car.id ? "Close" : "Edit"}
                </Button>
              ) : null}
            </div>
            <p className="text-muted-foreground text-xs">Next: {nextLine(car)}</p>
            {canWrite && editing === car.id ? (
              <CarForm
                slug={slug}
                contactId={contactId}
                car={car}
                onDone={() => setEditing(null)}
              />
            ) : null}
            {canWrite ? <ServiceForm slug={slug} carId={car.id} /> : null}
          </li>
        ))}
      </ul>
      {canWrite ? (
        adding ? (
          <CarForm slug={slug} contactId={contactId} car={null} onDone={() => setAdding(false)} />
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => setAdding(true)}
          >
            Add a car
          </Button>
        )
      ) : null}
    </div>
  );
}

// --- reminders list -------------------------------------------------------------------------

function DismissReminder({ slug, id }: { slug: string; id: string }) {
  const [, action, pending] = useActionState(dismissReminder.bind(null, slug, id), IDLE);
  return (
    <form action={action}>
      <Button type="submit" variant="ghost" size="sm" disabled={pending}>
        Dismiss
      </Button>
    </form>
  );
}

export function ReminderList({
  slug,
  items,
  canSend,
  canWrite,
}: {
  slug: string;
  items: Reminder[];
  canSend: boolean;
  canWrite: boolean;
}) {
  const [state, action, pending] = useActionState(sendReminders.bind(null, slug), IDLE);
  const sendable = (r: Reminder) => r.status === "pending" || r.status === "skipped";
  const formId = "send-reminders";
  return (
    <div className="flex flex-col gap-3">
      <FormStatus state={state} />
      <form id={formId} action={action} className="contents" />
      <ul className="divide-y rounded-2xl border" aria-label="Reminders">
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
                <Badge variant="secondary">{REMINDER_KIND_LABEL[r.kind]}</Badge>
                <Link
                  href={crmPath(slug, "contacts", r.contact_id)}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {r.contact_name}
                </Link>
                <span className="text-muted-foreground">
                  {r.car}
                  {r.registration ? ` · ${r.registration}` : ""}
                </span>
                <Badge variant={STATUS_VARIANT[r.status as ReminderStatus] ?? "outline"}>
                  {REMINDER_STATUS_LABEL[r.status as ReminderStatus] ?? r.status}
                </Badge>
              </p>
              <p className="text-muted-foreground text-xs">
                Due {formatDay(r.due_on)}
                {r.channel ? ` · sent by ${r.channel === "email" ? "email" : "WhatsApp"}` : null}
                {!r.has_phone && !r.has_email ? " · no phone or email" : null}
              </p>
              {reminderSkipReason(r.skip_reason) ? (
                <p className="text-xs">{reminderSkipReason(r.skip_reason)}</p>
              ) : null}
            </div>
            {canWrite && sendable(r) ? <DismissReminder slug={slug} id={r.id} /> : null}
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

// --- settings -------------------------------------------------------------------------------

type TemplateOption = { id: string; label: string; paramCount: number; body: string | null };

function KindFields({
  kind,
  settings,
  templates,
}: {
  kind: ReminderKind;
  settings: ReminderSettings;
  templates: TemplateOption[];
}) {
  const current = settings[kind];
  const [templateId, setTemplateId] = useState(current.template_id ?? "");
  const chosen = templates.find((t) => t.id === templateId);
  return (
    <fieldset className="flex flex-col gap-3 rounded-xl border p-4">
      <legend className="px-1 text-sm font-medium">{REMINDER_KIND_LABEL[kind]}</legend>
      <FormField id={`${kind}_days`} label="Days before the due date">
        <Input
          id={`${kind}_days`}
          name={`${kind}_days`}
          type="number"
          min={1}
          max={90}
          defaultValue={current.days}
          className="w-28"
        />
      </FormField>
      <FormField
        id={`${kind}_message`}
        label="Message"
        hint="Email, and WhatsApp within 24 hours of their last message. {name}, {car}, {registration} and {due} are filled in."
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
                    {REMINDER_PARAM_LABEL[k] ?? k}
                  </option>
                ))}
              </select>
            </FormField>
          ))
        : null}
    </fieldset>
  );
}

export function ReminderSettingsForm({
  slug,
  settings,
  templates,
}: {
  slug: string;
  settings: ReminderSettings;
  templates: TemplateOption[];
}) {
  const [state, action, pending] = useActionState(saveReminderSettings.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex max-w-xl flex-col gap-4">
      <FormStatus state={state} />
      {REMINDER_KINDS.map((kind) => (
        <KindFields key={kind} kind={kind} settings={settings} templates={templates} />
      ))}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
