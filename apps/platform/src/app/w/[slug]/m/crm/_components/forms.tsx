"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useEffect, useRef } from "react";

import { type Contact, type Customer, type Lead, STATUS_ACTION, type SubjectType } from "@/lib/crm";
import { IDLE } from "@/lib/form-state";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import {
  addNote,
  changeLeadStatus,
  createContact,
  createCustomer,
  createLead,
  setContactArchived,
  setCustomerArchived,
  setLeadArchived,
  updateContact,
  updateCustomer,
  updateLead,
} from "../actions";

const TEXTAREA_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-20 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none aria-invalid:border-destructive";

type Option = { id: string; label: string };

// --- customers -------------------------------------------------------------------------------

export function CustomerForm({ slug, customer }: { slug: string; customer?: Customer }) {
  const action = customer
    ? updateCustomer.bind(null, slug, customer.id)
    : createCustomer.bind(null, slug);
  const [state, formAction, pending] = useActionState(action, IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={formAction} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="name" label="Name" error={errors.name}>
        <Input id="name" name="name" defaultValue={customer?.name} required maxLength={200} />
      </FormField>
      <FormField id="kind" label="Type" error={errors.kind}>
        <select
          id="kind"
          name="kind"
          defaultValue={customer?.kind ?? "business"}
          className={SELECT_CLASS}
        >
          <option value="business">Business</option>
          <option value="individual">Individual</option>
        </select>
      </FormField>
      <FormField id="vat_number" label="VAT number" hint="Optional." error={errors.vat_number}>
        <Input
          id="vat_number"
          name="vat_number"
          defaultValue={customer?.vat_number ?? ""}
          maxLength={32}
        />
      </FormField>
      <FormField id="notes" label="Notes" error={errors.notes}>
        <textarea
          id="notes"
          name="notes"
          defaultValue={customer?.notes ?? ""}
          maxLength={2000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : customer ? "Save customer" : "Create customer"}
      </Button>
    </form>
  );
}

// --- contacts --------------------------------------------------------------------------------

export function ContactForm({
  slug,
  contact,
  customers,
}: {
  slug: string;
  contact?: Contact;
  customers: Option[];
}) {
  const action = contact
    ? updateContact.bind(null, slug, contact.id)
    : createContact.bind(null, slug);
  const [state, formAction, pending] = useActionState(action, IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={formAction} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="full_name" label="Full name" error={errors.full_name}>
        <Input
          id="full_name"
          name="full_name"
          defaultValue={contact?.full_name}
          required
          maxLength={200}
        />
      </FormField>
      <FormField
        id="email"
        label="Email"
        hint="An email or a phone number is required."
        error={errors.email}
      >
        <Input
          id="email"
          name="email"
          type="email"
          defaultValue={contact?.email ?? ""}
          autoComplete="off"
        />
      </FormField>
      <FormField
        id="phone"
        label="Phone"
        hint="With country code; 8-digit numbers are taken as Maltese (+356)."
        error={errors.phone}
      >
        <Input
          id="phone"
          name="phone"
          type="tel"
          defaultValue={contact?.phone ?? ""}
          autoComplete="off"
        />
      </FormField>
      <FormField id="customer_id" label="Customer" hint="Optional." error={errors.customer_id}>
        <select
          id="customer_id"
          name="customer_id"
          defaultValue={contact?.customer?.id ?? ""}
          className={SELECT_CLASS}
        >
          <option value="">No customer</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </FormField>
      <FormField id="notes" label="Notes" error={errors.notes}>
        <textarea
          id="notes"
          name="notes"
          defaultValue={contact?.notes ?? ""}
          maxLength={2000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : contact ? "Save contact" : "Create contact"}
      </Button>
    </form>
  );
}

// --- leads -----------------------------------------------------------------------------------

export function LeadForm({
  slug,
  contacts,
  contactId,
  me,
}: {
  slug: string;
  contacts: Option[];
  contactId?: string;
  me: string;
}) {
  const [state, formAction, pending] = useActionState(createLead.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={formAction} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="contact_id" label="Contact" error={errors.contact_id}>
        <select
          id="contact_id"
          name="contact_id"
          defaultValue={contactId ?? ""}
          required
          className={SELECT_CLASS}
        >
          <option value="" disabled>
            Choose a contact
          </option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </FormField>
      <FormField id="title" label="Title" hint="What the enquiry is about." error={errors.title}>
        <Input id="title" name="title" required maxLength={200} />
      </FormField>
      <FormField id="notes" label="Notes" error={errors.notes}>
        <textarea id="notes" name="notes" maxLength={2000} className={TEXTAREA_CLASS} />
      </FormField>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="owner_user_id" value={me} defaultChecked />
        Assign to me
      </label>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Creating…" : "Create lead"}
      </Button>
    </form>
  );
}

export function LeadStatusForm({ slug, lead }: { slug: string; lead: Lead }) {
  const [state, formAction, pending] = useActionState(
    changeLeadStatus.bind(null, slug, lead.id),
    IDLE,
  );
  const targets = lead.allowed_transitions;
  if (targets.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        {lead.archived_at
          ? "Restore this lead before changing its status."
          : "This lead is closed."}
      </p>
    );
  }
  const open = targets.filter((t) => t !== "lost");
  return (
    <div className="flex flex-col gap-3">
      <FormStatus state={state} />
      {open.length > 0 ? (
        <form action={formAction} className="flex flex-wrap gap-2">
          {open.map((target) => (
            <Button key={target} type="submit" name="status" value={target} disabled={pending}>
              {STATUS_ACTION[target]}
            </Button>
          ))}
        </form>
      ) : null}
      {targets.includes("lost") ? (
        <form action={formAction} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <input type="hidden" name="status" value="lost" />
          <FormField
            id="lost_reason"
            label="Reason lost"
            error={state.fieldErrors?.lost_reason}
            className="sm:w-80"
          >
            <Input id="lost_reason" name="lost_reason" maxLength={500} />
          </FormField>
          <Button type="submit" variant="outline" disabled={pending}>
            {STATUS_ACTION.lost}
          </Button>
        </form>
      ) : null}
    </div>
  );
}

export function LeadEditForm({ slug, lead }: { slug: string; lead: Lead }) {
  const [state, formAction, pending] = useActionState(updateLead.bind(null, slug, lead.id), IDLE);
  return (
    <form action={formAction} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="title" label="Title" error={state.fieldErrors?.title}>
        <Input id="title" name="title" defaultValue={lead.title} required maxLength={200} />
      </FormField>
      <FormField id="notes" label="Notes" error={state.fieldErrors?.notes}>
        <textarea
          id="notes"
          name="notes"
          defaultValue={lead.notes ?? ""}
          maxLength={2000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save lead"}
      </Button>
    </form>
  );
}

// --- notes and archiving ---------------------------------------------------------------------

export function NoteForm({
  slug,
  subjectType,
  subjectId,
}: {
  slug: string;
  subjectType: SubjectType;
  subjectId: string;
}) {
  const [state, formAction, pending] = useActionState(
    addNote.bind(null, slug, subjectType, subjectId),
    IDLE,
  );
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status === "ok") form.current?.reset();
  }, [state]);
  return (
    <form ref={form} action={formAction} className="flex flex-col gap-2" noValidate>
      <FormStatus state={state} />
      <FormField id={`note-${subjectId}`} label="Add a note" error={state.fieldErrors?.body}>
        <textarea
          id={`note-${subjectId}`}
          name="body"
          required
          maxLength={2000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Add note"}
      </Button>
    </form>
  );
}

export function ArchiveButton({
  slug,
  kind,
  id,
  archived,
}: {
  slug: string;
  kind: "contact" | "customer" | "lead";
  id: string;
  archived: boolean;
}) {
  const action =
    kind === "contact"
      ? setContactArchived.bind(null, slug, id, !archived)
      : kind === "lead"
        ? setLeadArchived.bind(null, slug, id, !archived)
        : setCustomerArchived.bind(null, slug, id, !archived);
  const [state, formAction, pending] = useActionState(action, IDLE);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        {archived ? `Restore ${kind}` : `Archive ${kind}`}
      </Button>
    </form>
  );
}
