"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useEffect, useRef } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import { createPriceList, createVatRate } from "../actions";

export function VatRateForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(createVatRate.bind(null, slug), IDLE);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status === "ok") form.current?.reset();
  }, [state]);
  const errors = state.fieldErrors ?? {};
  return (
    <form ref={form} action={action} className="flex max-w-md flex-col gap-3">
      <FormStatus state={state} />
      <FormField id="vat-code" label="VAT code" error={errors.code}>
        <Input id="vat-code" name="code" required maxLength={64} placeholder="STANDARD" />
      </FormField>
      <FormField id="vat-name" label="VAT name" error={errors.name}>
        <Input id="vat-name" name="name" required maxLength={100} />
      </FormField>
      <FormField id="vat-rate" label="Rate (%)" error={errors.rate_percent}>
        <Input
          id="vat-rate"
          name="rate_percent"
          required
          inputMode="decimal"
          pattern="\d{1,3}(\.\d{1,2})?"
          placeholder="18.00"
        />
      </FormField>
      <p className="text-muted-foreground text-xs">
        A rate cannot be changed after it is created; add a new code instead.
      </p>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Add VAT rate"}
      </Button>
    </form>
  );
}

export function PriceListForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(createPriceList.bind(null, slug), IDLE);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status === "ok") form.current?.reset();
  }, [state]);
  const errors = state.fieldErrors ?? {};
  return (
    <form ref={form} action={action} className="flex max-w-md flex-col gap-3">
      <FormStatus state={state} />
      <FormField id="pl-code" label="Price list code" error={errors.code}>
        <Input id="pl-code" name="code" required maxLength={64} placeholder="RETAIL" />
      </FormField>
      <FormField id="pl-name" label="Price list name" error={errors.name}>
        <Input id="pl-name" name="name" required maxLength={100} />
      </FormField>
      <FormField id="pl-vat" label="Prices are" error={errors.prices_include_vat}>
        <select id="pl-vat" name="prices_include_vat" className={SELECT_CLASS} defaultValue="true">
          <option value="true">Including VAT</option>
          <option value="false">Excluding VAT</option>
        </select>
      </FormField>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="is_default" value="true" />
        Make this the default price list
      </label>
      <p className="text-muted-foreground text-xs">
        Prices are in euro. Whether they include VAT cannot be changed later.
      </p>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Add price list"}
      </Button>
    </form>
  );
}
