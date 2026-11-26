"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass, textareaClass } from "@onyx/ui/lib/form-classes";
import { useActionState, useState } from "react";

import { euros } from "@/lib/automotive";
import { IDLE } from "@/lib/form-state";
import { formatDay } from "@/lib/reminders";
import {
  INSTALLMENT_LABEL,
  INSTALLMENT_VARIANT,
  METHOD_LABEL,
  type PaymentMethod,
  type Schedule,
} from "@/lib/schedules";

import { FormStatus } from "../../../settings/form-status";
import {
  createSchedule,
  recordPayment,
  updateInstallment,
  updateSchedule,
  voidPayment,
} from "../schedule-actions";

const METHODS = Object.keys(METHOD_LABEL) as PaymentMethod[];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function eurosValue(cents: number | null | undefined): string {
  return cents ? (cents / 100).toFixed(2) : "";
}

export function NewScheduleForm({
  slug,
  deal,
  contacts,
  defaults,
}: {
  slug: string;
  deal: { id: string; title: string } | null;
  contacts: { id: string; label: string }[];
  defaults: {
    total_cents: number | null;
    term_months: number | null;
    monthly_cents: number | null;
  };
}) {
  const [state, action, pending] = useActionState(createSchedule.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4">
      <FormStatus state={state} />
      {deal ? (
        <>
          <input type="hidden" name="deal_id" value={deal.id} />
          <p className="text-sm">
            For the deal <strong>{deal.title}</strong>. Amounts come from its approved finance
            application when you leave them empty.
          </p>
        </>
      ) : (
        <FormField id="contact_id" label="Customer" error={state.fieldErrors?.contact_id}>
          <select id="contact_id" name="contact_id" className={selectClass} defaultValue="">
            <option value="" disabled>
              Choose a customer
            </option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </FormField>
      )}
      <FormField
        id="label"
        label="Car"
        hint={deal ? "Leave empty to use the deal title." : undefined}
        error={state.fieldErrors?.label}
      >
        <Input id="label" name="label" maxLength={200} placeholder="Toyota Yaris 2018" />
      </FormField>
      <FormField
        id="total"
        label="Amount to repay (€)"
        hint="Everything the customer pays back, including interest and fees."
        error={state.fieldErrors?.total_cents}
      >
        <Input
          id="total"
          name="total"
          inputMode="decimal"
          defaultValue={eurosValue(defaults.total_cents)}
        />
      </FormField>
      <FormField id="term_months" label="Term (months)" error={state.fieldErrors?.term_months}>
        <Input
          id="term_months"
          name="term_months"
          type="number"
          min={1}
          max={120}
          defaultValue={defaults.term_months ?? ""}
          className="w-28"
        />
      </FormField>
      <FormField
        id="monthly"
        label="Monthly amount (€)"
        hint="Optional. Leave empty to split the total evenly; the last month takes the difference."
        error={state.fieldErrors?.monthly_cents}
      >
        <Input
          id="monthly"
          name="monthly"
          inputMode="decimal"
          defaultValue={eurosValue(defaults.monthly_cents)}
        />
      </FormField>
      <FormField
        id="first_due_on"
        label="First payment due"
        error={state.fieldErrors?.first_due_on}
      >
        <Input id="first_due_on" name="first_due_on" type="date" className="w-44" />
      </FormField>
      <FormField id="note" label="Note" error={state.fieldErrors?.note}>
        <textarea id="note" name="note" maxLength={500} className={`${textareaClass} min-h-16`} />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Creating…" : "Create schedule"}
      </Button>
    </form>
  );
}

export function PaymentForm({ slug, scheduleId }: { slug: string; scheduleId: string }) {
  const [state, action, pending] = useActionState(recordPayment.bind(null, slug, scheduleId), IDLE);
  return (
    <form action={action} className="flex flex-col gap-3" aria-label="Record a payment">
      <FormStatus state={state} />
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField id="amount" label="Amount (€)" error={state.fieldErrors?.amount_cents}>
          <Input id="amount" name="amount" inputMode="decimal" />
        </FormField>
        <FormField id="received_on" label="Received on" error={state.fieldErrors?.received_on}>
          <Input id="received_on" name="received_on" type="date" defaultValue={todayIso()} />
        </FormField>
        <FormField id="method" label="Method">
          <select id="method" name="method" className={selectClass} defaultValue="bank_transfer">
            {METHODS.map((m) => (
              <option key={m} value={m}>
                {METHOD_LABEL[m]}
              </option>
            ))}
          </select>
        </FormField>
      </div>
      <FormField id="payment-note" label="Note (optional)">
        <Input id="payment-note" name="note" maxLength={300} />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start" size="sm">
        {pending ? "Saving…" : "Record payment"}
      </Button>
    </form>
  );
}

function VoidForm({
  slug,
  scheduleId,
  paymentId,
}: {
  slug: string;
  scheduleId: string;
  paymentId: string;
}) {
  const [open, setOpen] = useState(false);
  const [state, action, pending] = useActionState(
    voidPayment.bind(null, slug, scheduleId, paymentId),
    IDLE,
  );
  if (!open) {
    return (
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(true)}>
        Void
      </Button>
    );
  }
  return (
    <form action={action} className="flex flex-wrap items-end gap-2">
      <FormStatus state={state} />
      <FormField id={`void-${paymentId}`} label="Why?" error={state.fieldErrors?.reason}>
        <Input id={`void-${paymentId}`} name="reason" maxLength={300} placeholder="Entered twice" />
      </FormField>
      <Button type="submit" variant="outline" size="sm" disabled={pending}>
        {pending ? "Voiding…" : "Void payment"}
      </Button>
    </form>
  );
}

function InstallmentEdit({
  slug,
  scheduleId,
  installment,
}: {
  slug: string;
  scheduleId: string;
  installment: Schedule["installments"][number];
}) {
  const [open, setOpen] = useState(false);
  const [state, action, pending] = useActionState(
    updateInstallment.bind(null, slug, scheduleId, installment.id),
    IDLE,
  );
  if (!open) {
    return (
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(true)}>
        Change
      </Button>
    );
  }
  return (
    <form action={action} className="flex flex-wrap items-end gap-2">
      <FormStatus state={state} />
      <FormField id={`due-${installment.id}`} label="Due on">
        <Input
          id={`due-${installment.id}`}
          name="due_on"
          type="date"
          defaultValue={installment.due_on}
        />
      </FormField>
      <FormField
        id={`amount-${installment.id}`}
        label="Amount (€)"
        error={state.fieldErrors?.amount_cents}
      >
        <Input
          id={`amount-${installment.id}`}
          name="amount"
          inputMode="decimal"
          defaultValue={eurosValue(installment.amount_cents)}
          className="w-28"
        />
      </FormField>
      <Button type="submit" variant="outline" size="sm" disabled={pending}>
        Save
      </Button>
    </form>
  );
}

export function InstallmentTable({
  slug,
  schedule,
  canManage,
}: {
  slug: string;
  schedule: Schedule;
  canManage: boolean;
}) {
  return (
    <ul className="divide-y" aria-label="Installments">
      {schedule.installments.map((i) => (
        <li key={i.id} className="flex flex-wrap items-center gap-3 px-5 py-2.5 text-sm">
          <span className="text-muted-foreground w-8 tabular-nums">{i.number}</span>
          <span className="w-24 tabular-nums">{formatDay(i.due_on)}</span>
          <span className="w-28 tabular-nums">{euros(i.amount_cents)}</span>
          {i.paid_cents > 0 && i.paid_cents < i.amount_cents ? (
            <span className="text-muted-foreground text-xs">{euros(i.paid_cents)} paid</span>
          ) : null}
          <Badge variant={INSTALLMENT_VARIANT[i.state]} className="ml-auto">
            {INSTALLMENT_LABEL[i.state]}
          </Badge>
          {canManage && i.state !== "paid" ? (
            <InstallmentEdit slug={slug} scheduleId={schedule.id} installment={i} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function PaymentList({
  slug,
  schedule,
  canManage,
}: {
  slug: string;
  schedule: Schedule;
  canManage: boolean;
}) {
  if (schedule.payments.length === 0) {
    return <p className="text-muted-foreground px-5 py-4 text-sm">No payments recorded yet.</p>;
  }
  return (
    <ul className="divide-y" aria-label="Payments">
      {schedule.payments.map((p) => (
        <li key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-2.5 text-sm">
          <span className={`w-28 tabular-nums ${p.voided ? "line-through" : ""}`}>
            {euros(p.amount_cents)}
          </span>
          <span className="w-24 tabular-nums">{formatDay(p.received_on)}</span>
          <span className="text-muted-foreground">{METHOD_LABEL[p.method]}</span>
          {p.note ? <span className="text-muted-foreground text-xs">{p.note}</span> : null}
          {p.voided ? (
            <Badge variant="outline" className="ml-auto">
              Voided{p.void_reason ? `: ${p.void_reason}` : ""}
            </Badge>
          ) : canManage ? (
            <span className="ml-auto">
              <VoidForm slug={slug} scheduleId={schedule.id} paymentId={p.id} />
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function ScheduleSettingsForm({ slug, schedule }: { slug: string; schedule: Schedule }) {
  const [state, action, pending] = useActionState(
    updateSchedule.bind(null, slug, schedule.id),
    IDLE,
  );
  return (
    <form action={action} className="flex flex-col gap-3">
      <FormStatus state={state} />
      <FormField id="schedule-label" label="Car" error={state.fieldErrors?.label}>
        <Input id="schedule-label" name="label" maxLength={200} defaultValue={schedule.label} />
      </FormField>
      <FormField id="schedule-note" label="Note">
        <textarea
          id="schedule-note"
          name="note"
          maxLength={500}
          defaultValue={schedule.note ?? ""}
          className={`${textareaClass} min-h-16`}
        />
      </FormField>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="reminders_paused" defaultChecked={schedule.reminders_paused} />
        Pause payment reminders
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="cancelled" defaultChecked={schedule.status === "cancelled"} />
        Cancelled
      </label>
      <Button type="submit" variant="outline" size="sm" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
