"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState } from "react";

import { type FormState, createInvitation } from "../actions";
import { FormStatus, SELECT_CLASS } from "../form-status";

const INITIAL: FormState = { status: "idle" };

export function InviteForm({ slug, canInviteOwner }: { slug: string; canInviteOwner: boolean }) {
  const [state, action, pending] = useActionState(createInvitation.bind(null, slug), INITIAL);
  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      {state.inviteLink ? (
        <FormField id="invite-link" label="One-time invitation link">
          <Input id="invite-link" readOnly value={state.inviteLink} className="font-mono text-xs" />
        </FormField>
      ) : null}
      <FormField id="invite-email" label="Email" error={state.fieldErrors?.email}>
        <Input id="invite-email" name="email" type="email" autoComplete="off" required />
      </FormField>
      <FormField id="invite-role" label="Role" error={state.fieldErrors?.role}>
        <select id="invite-role" name="role" defaultValue="member" className={SELECT_CLASS}>
          <option value="member">Member</option>
          <option value="admin">Admin</option>
          {canInviteOwner ? <option value="owner">Owner</option> : null}
        </select>
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Inviting…" : "Create invitation"}
      </Button>
    </form>
  );
}
