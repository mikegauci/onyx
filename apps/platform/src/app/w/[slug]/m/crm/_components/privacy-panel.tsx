"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { Download } from "lucide-react";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { eraseContact } from "../privacy-actions";

/** Owners only: export a person's data, or erase it everywhere (cannot be undone). */
export function PrivacyPanel({
  slug,
  contactId,
  fullName,
  exportHref,
  erasedAt,
}: {
  slug: string;
  contactId: string;
  fullName: string;
  exportHref: string;
  erasedAt: string | null;
}) {
  const [state, action, pending] = useActionState(eraseContact.bind(null, slug, contactId), IDLE);
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground text-sm">
          Download everything Onyx holds about this person (for a data access request).
        </p>
        <a
          href={exportHref}
          className="border-foreground/15 hover:bg-foreground/[0.05] focus-visible:ring-ring inline-flex h-8 items-center gap-1.5 self-start rounded-full border px-3 text-[13px] font-medium focus-visible:ring-2 focus-visible:outline-none"
        >
          <Download aria-hidden className="size-4" />
          Download their data
        </a>
      </div>
      {erasedAt ? (
        <p className="text-sm">This person’s data was erased.</p>
      ) : (
        <form
          action={action}
          className="flex flex-col gap-3 border-t pt-5"
          aria-label="Erase this person"
        >
          <FormStatus state={state} />
          <p className="text-sm">
            <strong className="font-medium">Erase this person.</strong>{" "}
            <span className="text-muted-foreground">
              Removes their name, contact details, messages, notes and deal documents everywhere in
              Onyx. Amounts, dates and quote numbers stay for your records, and an opt-out (STOP)
              stays so they are not messaged again. This cannot be undone.
            </span>
          </p>
          <FormField
            id="confirm-name"
            label={`Type “${fullName}” to confirm`}
            error={state.fieldErrors?.confirm_name}
          >
            <Input id="confirm-name" name="confirm_name" autoComplete="off" />
          </FormField>
          <Button type="submit" variant="destructive" disabled={pending} className="self-start">
            {pending ? "Erasing…" : "Erase this person"}
          </Button>
        </form>
      )}
    </div>
  );
}
