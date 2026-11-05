"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { type ImportResult, type LeadStatus, type SubjectType, crmPath } from "@/lib/crm";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

const MAX_FILE_BYTES = 1_000_000;

function done(slug: string, message: string): FormState {
  revalidatePath(crmPath(slug), "layout");
  return { status: "ok", message };
}

// --- customers -------------------------------------------------------------------------------

function customerBody(formData: FormData) {
  return {
    name: text(formData, "name"),
    kind: text(formData, "kind") === "individual" ? ("individual" as const) : ("business" as const),
    vat_number: optionalText(formData, "vat_number"),
    notes: optionalText(formData, "notes"),
  };
}

export async function createCustomer(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/customers", {
      params: { path: { slug } },
      body: customerBody(formData),
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(crmPath(slug), "layout");
  redirect(crmPath(slug, "customers", outcome.data.id));
}

export async function updateCustomer(
  slug: string,
  customerId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/crm/customers/{customer_id}", {
      params: { path: { slug, customer_id: customerId } },
      body: customerBody(formData),
    }),
  );
  return outcome.ok ? done(slug, "Customer saved.") : failureState(outcome);
}

export async function setCustomerArchived(
  slug: string,
  customerId: string,
  archived: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/customers/{customer_id}/archive", {
      params: { path: { slug, customer_id: customerId } },
      body: { archived },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, archived ? "Customer archived." : "Customer restored.");
}

// --- contacts --------------------------------------------------------------------------------

function contactBody(formData: FormData) {
  return {
    full_name: text(formData, "full_name"),
    email: optionalText(formData, "email"),
    phone: optionalText(formData, "phone"),
    customer_id: optionalText(formData, "customer_id"),
    notes: optionalText(formData, "notes"),
  };
}

export async function createContact(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/contacts", {
      params: { path: { slug } },
      body: contactBody(formData),
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(crmPath(slug), "layout");
  redirect(crmPath(slug, "contacts", outcome.data.id));
}

export async function updateContact(
  slug: string,
  contactId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/crm/contacts/{contact_id}", {
      params: { path: { slug, contact_id: contactId } },
      body: contactBody(formData),
    }),
  );
  return outcome.ok ? done(slug, "Contact saved.") : failureState(outcome);
}

export async function setContactArchived(
  slug: string,
  contactId: string,
  archived: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/contacts/{contact_id}/archive", {
      params: { path: { slug, contact_id: contactId } },
      body: { archived },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, archived ? "Contact archived." : "Contact restored.");
}

// --- leads -----------------------------------------------------------------------------------

export async function createLead(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/leads", {
      params: { path: { slug } },
      body: {
        contact_id: text(formData, "contact_id"),
        title: text(formData, "title"),
        source: "manual",
        notes: optionalText(formData, "notes"),
        owner_user_id: optionalText(formData, "owner_user_id"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(crmPath(slug), "layout");
  redirect(crmPath(slug, "leads", outcome.data.id));
}

export async function changeLeadStatus(
  slug: string,
  leadId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const status = text(formData, "status") as LeadStatus;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/leads/{lead_id}/status", {
      params: { path: { slug, lead_id: leadId } },
      body: { status, lost_reason: optionalText(formData, "lost_reason") },
    }),
  );
  return outcome.ok ? done(slug, "Status updated.") : failureState(outcome);
}

export async function updateLead(
  slug: string,
  leadId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/crm/leads/{lead_id}", {
      params: { path: { slug, lead_id: leadId } },
      body: { title: text(formData, "title"), notes: optionalText(formData, "notes") },
    }),
  );
  return outcome.ok ? done(slug, "Lead saved.") : failureState(outcome);
}

export async function setLeadArchived(
  slug: string,
  leadId: string,
  archived: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/leads/{lead_id}/archive", {
      params: { path: { slug, lead_id: leadId } },
      body: { archived },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, archived ? "Lead archived." : "Lead restored.");
}

// --- notes -----------------------------------------------------------------------------------

export async function addNote(
  slug: string,
  subjectType: SubjectType,
  subjectId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/notes", {
      params: { path: { slug } },
      body: { subject_type: subjectType, subject_id: subjectId, body: text(formData, "body") },
    }),
  );
  return outcome.ok ? done(slug, "Note added.") : failureState(outcome);
}

// --- import ----------------------------------------------------------------------------------

export type ImportState = FormState & { result?: ImportResult; csv?: string; fileName?: string };

/**
 * Step 1 (`intent=preview`): read the chosen file and ask the API for a dry run.
 * Step 2 (`intent=import`): send the same text again with `dry_run: false`.
 */
export async function importContacts(
  slug: string,
  prev: ImportState,
  formData: FormData,
): Promise<ImportState> {
  const intent = text(formData, "intent");
  let csv: string;
  let fileName: string | undefined;
  if (intent === "import") {
    csv = prev.csv ?? "";
    fileName = prev.fileName;
  } else {
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) {
      return { status: "error", message: "Choose a CSV file.", fieldErrors: { file: "Required." } };
    }
    if (file.size > MAX_FILE_BYTES) {
      return {
        status: "error",
        message: "The file is larger than 1 MB.",
        fieldErrors: { file: "Too large." },
      };
    }
    csv = await file.text();
    fileName = file.name;
  }
  const dryRun = intent !== "import";
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/crm/contacts/import", {
      params: { path: { slug } },
      body: { csv, dry_run: dryRun },
    }),
  );
  if (!outcome.ok) {
    const failure = failureState(outcome);
    return {
      ...failure,
      fieldErrors: failure.fieldErrors?.csv
        ? { file: failure.fieldErrors.csv }
        : failure.fieldErrors,
    };
  }
  const result = outcome.data;
  if (dryRun) {
    return {
      status: "ok",
      message: `Preview of ${fileName ?? "the file"}: nothing has been saved yet.`,
      result,
      csv,
      fileName,
    };
  }
  revalidatePath(crmPath(slug), "layout");
  return {
    status: "ok",
    message: `Imported ${result.contacts_created} contacts, ${result.customers_created} customers and ${result.leads_created} leads.`,
    result,
  };
}
