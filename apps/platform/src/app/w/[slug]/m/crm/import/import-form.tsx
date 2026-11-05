"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { crmPath } from "@/lib/crm";
import { FormStatus } from "../../../settings/form-status";
import { importContacts, type ImportState } from "../actions";

const INITIAL: ImportState = { status: "idle" };

export function ImportForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(importContacts.bind(null, slug), INITIAL);
  const result = state.result;
  return (
    <div className="flex flex-col gap-4">
      <FormStatus state={state} />
      <form action={action} className="flex flex-col items-start gap-3">
        <FormField id="file" label="Contacts CSV" error={state.fieldErrors?.file}>
          <Input id="file" name="file" type="file" accept=".csv,text/csv" disabled={pending} />
        </FormField>
        <Button type="submit" name="intent" value="preview" variant="outline" disabled={pending}>
          {pending ? "Working…" : "Preview CSV"}
        </Button>
      </form>
      {result ? (
        <section className="flex flex-col gap-3" aria-label="Import results">
          <p>
            {result.total} rows · {result.contacts_created} contacts · {result.customers_created}{" "}
            customers · {result.leads_created} leads
            {result.dry_run ? " ready to import" : " created"}.
          </p>
          {result.errors.length > 0 ? (
            <div>
              <h3 className="font-medium">Rows with errors</h3>
              <ul className="list-inside list-disc text-sm">
                {result.errors.map((error, i) => (
                  <li key={i}>
                    Row {error.row}, {error.field}: {error.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.duplicates.length > 0 ? (
            <div>
              <h3 className="font-medium">Duplicates skipped</h3>
              <ul className="list-inside list-disc text-sm">
                {result.duplicates.map((duplicate, i) => (
                  <li key={i}>
                    Row {duplicate.row}: {duplicate.field} already used
                    {duplicate.first_row ? ` in row ${duplicate.first_row}` : ""}.{" "}
                    {duplicate.existing_contact_id ? (
                      <Link
                        className="underline"
                        href={crmPath(slug, "contacts", duplicate.existing_contact_id)}
                      >
                        View existing contact
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.dry_run && state.csv && result.contacts_created > 0 ? (
            <form action={action}>
              <Button type="submit" name="intent" value="import" disabled={pending}>
                {pending ? "Importing…" : "Import valid rows"}
              </Button>
            </form>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
