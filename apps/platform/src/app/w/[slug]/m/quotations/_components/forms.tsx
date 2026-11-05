"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useEffect, useRef } from "react";

import { IDLE } from "@/lib/form-state";
import type { QuoteDetail, QuoteLine, QuotationSettings, QuoteWarning } from "@/lib/quotations";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import {
  addCustomLine,
  addSkuLine,
  approveQuote,
  createQuote,
  quoteAction,
  refreshLine,
  removeLine,
  saveSettings,
  updateLine,
  updateQuote,
} from "../actions";

const TEXTAREA_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-20 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none aria-invalid:border-destructive";

type Option = { id: string; label: string };

function useResetOnSuccess(status: string) {
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (status === "ok") form.current?.reset();
  }, [status]);
  return form;
}

export function NewQuoteForm({
  slug,
  contacts,
  leads,
}: {
  slug: string;
  contacts: Option[];
  leads: Option[];
}) {
  const [state, action, pending] = useActionState(createQuote.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="title" label="Title" error={errors.title}>
        <Input id="title" name="title" required maxLength={200} />
      </FormField>
      <FormField id="contact_id" label="Contact" error={errors.contact_id}>
        <select id="contact_id" name="contact_id" className={SELECT_CLASS} required>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </FormField>
      <FormField id="lead_id" label="Lead (optional)" error={errors.lead_id}>
        <select id="lead_id" name="lead_id" className={SELECT_CLASS} defaultValue="">
          <option value="">No lead</option>
          {leads.map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
        </select>
      </FormField>
      <p className="text-muted-foreground text-xs">
        The quote uses the default price list. Prices are copied when you add each line.
      </p>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Create draft quote"}
      </Button>
    </form>
  );
}

export function QuoteHeaderForm({ slug, quote }: { slug: string; quote: QuoteDetail }) {
  const [state, action, pending] = useActionState(updateQuote.bind(null, slug, quote.id), IDLE);
  return (
    <form action={action} className="flex max-w-xl flex-col gap-3" noValidate>
      <FormStatus state={state} />
      <FormField id="quote-title" label="Title" error={state.fieldErrors?.title}>
        <Input id="quote-title" name="title" defaultValue={quote.title} maxLength={200} />
      </FormField>
      <FormField id="quote-notes" label="Notes for the customer" error={state.fieldErrors?.notes}>
        <textarea
          id="quote-notes"
          name="notes"
          defaultValue={quote.notes ?? ""}
          maxLength={2000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        Save details
      </Button>
    </form>
  );
}

export function AddSkuForm({ slug, quoteId }: { slug: string; quoteId: string }) {
  const [state, action, pending] = useActionState(addSkuLine.bind(null, slug, quoteId), IDLE);
  const form = useResetOnSuccess(state.status);
  const errors = state.fieldErrors ?? {};
  return (
    <form ref={form} action={action} className="flex flex-col gap-2" noValidate>
      <FormStatus state={state} />
      <div className="flex flex-wrap items-end gap-2">
        <FormField
          id="add-sku"
          label="SKU"
          error={errors.sku ?? errors.variant_id}
          className="w-44"
        >
          <Input id="add-sku" name="sku" required maxLength={64} placeholder="ARC-P-30-BRS" />
        </FormField>
        <FormField id="add-qty" label="Quantity" error={errors.quantity} className="w-24">
          <Input id="add-qty" name="quantity" type="number" min={1} defaultValue={1} />
        </FormField>
        <FormField
          id="add-discount"
          label="Discount %"
          error={errors.discount_percent}
          className="w-28"
        >
          <Input id="add-discount" name="discount_percent" inputMode="decimal" defaultValue="0" />
        </FormField>
        <Button type="submit" disabled={pending}>
          Add SKU
        </Button>
      </div>
    </form>
  );
}

export function AddCustomLineForm({
  slug,
  quoteId,
  vatRates,
}: {
  slug: string;
  quoteId: string;
  vatRates: Option[];
}) {
  const [state, action, pending] = useActionState(addCustomLine.bind(null, slug, quoteId), IDLE);
  const form = useResetOnSuccess(state.status);
  const errors = state.fieldErrors ?? {};
  return (
    <form ref={form} action={action} className="flex flex-col gap-2" noValidate>
      <FormStatus state={state} />
      <div className="flex flex-wrap items-end gap-2">
        <FormField
          id="custom-description"
          label="Service"
          error={errors.description}
          className="w-64"
        >
          <Input id="custom-description" name="description" required maxLength={300} />
        </FormField>
        <FormField
          id="custom-price"
          label="Unit price (€)"
          error={errors.unit_price}
          className="w-28"
        >
          <Input id="custom-price" name="unit_price" inputMode="decimal" placeholder="80.00" />
        </FormField>
        <FormField id="custom-vat" label="VAT" error={errors.vat_rate_id} className="w-40">
          <select id="custom-vat" name="vat_rate_id" className={SELECT_CLASS}>
            {vatRates.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </FormField>
        <FormField id="custom-qty" label="Quantity" error={errors.quantity} className="w-24">
          <Input id="custom-qty" name="quantity" type="number" min={1} defaultValue={1} />
        </FormField>
        <Button type="submit" variant="outline" disabled={pending}>
          Add service line
        </Button>
      </div>
    </form>
  );
}

export function LineControls({
  slug,
  quoteId,
  line,
  warnings,
}: {
  slug: string;
  quoteId: string;
  line: QuoteLine;
  warnings: QuoteWarning[];
}) {
  const [state, update, pending] = useActionState(
    updateLine.bind(null, slug, quoteId, line.id),
    IDLE,
  );
  const [refreshState, refresh, refreshing] = useActionState(
    refreshLine.bind(null, slug, quoteId, line.id),
    IDLE,
  );
  const [removeState, remove, removing] = useActionState(
    removeLine.bind(null, slug, quoteId, line.id),
    IDLE,
  );
  const label = line.sku ?? line.description;
  return (
    <div className="flex flex-col gap-2">
      {[state, refreshState, removeState].map((s, i) => (
        <FormStatus key={i} state={s} />
      ))}
      <form action={update} className="flex flex-wrap items-end gap-2">
        <FormField
          id={`qty-${line.id}`}
          label="Qty"
          className="w-20"
          error={state.fieldErrors?.quantity}
        >
          <Input
            id={`qty-${line.id}`}
            name="quantity"
            type="number"
            min={1}
            defaultValue={line.quantity}
            aria-label={`Quantity for ${label}`}
          />
        </FormField>
        <FormField
          id={`disc-${line.id}`}
          label="Disc. %"
          className="w-24"
          error={state.fieldErrors?.discount_percent}
        >
          <Input
            id={`disc-${line.id}`}
            name="discount_percent"
            inputMode="decimal"
            defaultValue={String(line.discount_percent)}
            aria-label={`Discount for ${label}`}
          />
        </FormField>
        <Button type="submit" size="sm" variant="outline" disabled={pending}>
          Update
        </Button>
      </form>
      <div className="flex gap-2">
        {warnings.some((w) => w.blocking) && line.kind === "catalogue" ? (
          <form action={refresh}>
            <Button
              type="submit"
              size="sm"
              disabled={refreshing}
              aria-label={`Use current price for ${label}`}
            >
              Use current price
            </Button>
          </form>
        ) : null}
        <form action={remove}>
          <Button
            type="submit"
            size="sm"
            variant="ghost"
            disabled={removing}
            aria-label={`Remove ${label}`}
          >
            Remove
          </Button>
        </form>
      </div>
    </div>
  );
}

export function ApproveForm({ slug, quote }: { slug: string; quote: QuoteDetail }) {
  const [state, action, pending] = useActionState(
    approveQuote.bind(null, slug, quote.id, quote.version),
    IDLE,
  );
  const blocking = quote.warnings.filter((w) => w.blocking);
  const confirmable = quote.warnings.filter((w) => !w.blocking);
  const lineLabel = (id: string) => {
    const line = quote.lines.find((l) => l.id === id);
    return line?.sku ?? line?.description ?? "line";
  };
  return (
    <form action={action} className="flex flex-col gap-3 rounded-md border p-4">
      <h3 className="font-medium">Approve version {quote.version}</h3>
      <FormStatus state={state} />
      {blocking.length > 0 ? (
        <p className="text-destructive text-sm">
          Fix the lines marked as blocking first: use the current price or remove them.
        </p>
      ) : null}
      {confirmable.length > 0 ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium">Confirm before approving</legend>
          {confirmable.map((w) => (
            <label key={`${w.line_id}:${w.code}`} className="flex items-center gap-2 text-sm">
              <input type="checkbox" name="acknowledge" value={`${w.line_id}:${w.code}`} />
              {lineLabel(w.line_id)}: {w.message}
            </label>
          ))}
        </fieldset>
      ) : null}
      <Button
        type="submit"
        disabled={pending || blocking.length > 0 || quote.lines.length === 0}
        className="self-start"
      >
        {pending ? "Approving…" : "Approve quote"}
      </Button>
      <p className="text-muted-foreground text-xs">
        Approving freezes this version&apos;s prices and totals. Nothing is sent to the customer.
      </p>
    </form>
  );
}

export function QuoteActions({ slug, quote }: { slug: string; quote: QuoteDetail }) {
  const [state, action, pending] = useActionState(quoteAction.bind(null, slug, quote.id), IDLE);
  const actions = quote.allowed_actions.filter((a) =>
    ["accept", "decline", "revise", "cancel"].includes(a),
  );
  if (actions.length === 0) return null;
  const LABEL: Record<string, string> = {
    accept: "Record accepted",
    decline: "Record declined",
    revise: "Revise (new version)",
    cancel: "Cancel quote",
  };
  return (
    <form action={action} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <FormField
        id="reason"
        label="Reason (optional, for declined or cancelled)"
        className="max-w-md"
      >
        <Input id="reason" name="reason" maxLength={500} />
      </FormField>
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Button
            key={a}
            type="submit"
            name="action"
            value={a}
            disabled={pending}
            variant={a === "accept" || a === "revise" ? "default" : "outline"}
          >
            {LABEL[a]}
          </Button>
        ))}
      </div>
    </form>
  );
}

export function SettingsForm({ slug, settings }: { slug: string; settings: QuotationSettings }) {
  const [state, action, pending] = useActionState(saveSettings.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex max-w-md flex-col gap-3" noValidate>
      <FormStatus state={state} />
      <FormField id="number_prefix" label="Quote number prefix" error={errors.number_prefix}>
        <Input
          id="number_prefix"
          name="number_prefix"
          defaultValue={settings.number_prefix}
          maxLength={10}
          pattern="[A-Z]{1,10}"
        />
      </FormField>
      <FormField id="validity_days" label="Valid for (days)" error={errors.validity_days}>
        <Input
          id="validity_days"
          name="validity_days"
          type="number"
          min={1}
          max={365}
          defaultValue={settings.validity_days}
        />
      </FormField>
      <FormField
        id="max_discount_percent"
        label="Largest discount members may give (%)"
        error={errors.max_discount_percent}
      >
        <Input
          id="max_discount_percent"
          name="max_discount_percent"
          inputMode="decimal"
          defaultValue={String(settings.max_discount_percent)}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save settings"}
      </Button>
    </form>
  );
}
