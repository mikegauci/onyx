"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass } from "@onyx/ui/lib/form-classes";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { createDeal } from "../actions";

type Option = { id: string; label: string };

export function NewDealForm({
  slug,
  contacts,
  vehicles,
  defaults,
}: {
  slug: string;
  contacts: Option[];
  vehicles: Option[] | null;
  defaults: { contactId: string; quoteId: string; leadId: string; conversationId: string };
}) {
  const [state, action, pending] = useActionState(createDeal.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <input type="hidden" name="quote_id" value={defaults.quoteId} />
      <input type="hidden" name="lead_id" value={defaults.leadId} />
      <input type="hidden" name="conversation_id" value={defaults.conversationId} />
      {defaults.quoteId ? (
        <p className="text-muted-foreground text-sm">
          From an accepted quote: the customer comes from the quote.
        </p>
      ) : (
        <FormField id="deal-contact" label="Customer" error={errors.contact_id}>
          <select
            id="deal-contact"
            name="contact_id"
            defaultValue={defaults.contactId}
            className={selectClass}
            required
          >
            <option value="">Choose a contact</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </FormField>
      )}
      {vehicles ? (
        <FormField
          id="deal-vehicle"
          label="Car"
          hint="Only available cars are listed."
          error={errors.vehicle_id}
        >
          <select id="deal-vehicle" name="vehicle_id" defaultValue="" className={selectClass}>
            <option value="">No car (or not in stock)</option>
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </FormField>
      ) : null}
      <FormField
        id="deal-title"
        label="Title (optional)"
        hint="Defaults to the customer and the car."
        error={errors.title}
      >
        <Input id="deal-title" name="title" maxLength={200} />
      </FormField>
      <FormField
        id="deal-price"
        label="Agreed price (€, optional)"
        hint="Defaults to the car's listed price."
        error={errors.price ?? errors.price_cents}
      >
        <Input id="deal-price" name="price" inputMode="decimal" className="max-w-48" />
      </FormField>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">This sale</legend>
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" name="financed" className="accent-brand size-4" />
          Financed in-house (adds the finance papers to the checklist)
        </label>
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" name="has_trade_in" className="accent-brand size-4" />
          Includes a trade-in (adds the trade-in logbook)
        </label>
      </fieldset>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Creating…" : "Create deal"}
      </Button>
    </form>
  );
}
