"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";
import {
  type AdminInvitation,
  INVITATION_STATE_LABEL,
  INVITATION_STATE_VARIANT,
} from "@/lib/tenants";

import { FormStatus, SELECT_CLASS } from "../../../w/[slug]/settings/form-status";
import {
  type AdminFormState,
  issueInvitation,
  revokeInvitation,
  setAIBudget,
  setOrganizationStatus,
  updateOrganization,
} from "../actions";
import { BrandColorField, CopyLink } from "@/components/brand-fields";

type Details = {
  slug: string;
  name: string;
  timezone: string;
  display_name: string | null;
  brand_color: string | null;
};

export function DetailsForm({ org, timezones }: { org: Details; timezones: string[] }) {
  const [state, action, pending] = useActionState(updateOrganization.bind(null, org.slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <FormField id="admin-name" label="Organisation name" error={errors.name}>
        <Input id="admin-name" name="name" required maxLength={200} defaultValue={org.name} />
      </FormField>
      <FormField id="admin-timezone" label="Timezone" error={errors.timezone}>
        <select
          id="admin-timezone"
          name="timezone"
          defaultValue={org.timezone}
          className={SELECT_CLASS}
        >
          {timezones.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </FormField>
      <FormField
        id="admin-display"
        label="Display name"
        hint="Optional. Empty uses the organisation name."
        error={errors.display_name}
      >
        <Input
          id="admin-display"
          name="display_name"
          maxLength={200}
          defaultValue={org.display_name ?? ""}
        />
      </FormField>
      <BrandColorField
        id="admin-color"
        error={errors.brand_color}
        defaultValue={org.brand_color ?? ""}
      />
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save details"}
      </Button>
    </form>
  );
}

export function StatusControl({
  slug,
  name,
  status,
}: {
  slug: string;
  name: string;
  status: string;
}) {
  const suspended = status === "suspended";
  const [state, action, pending] = useActionState(
    setOrganizationStatus.bind(null, slug, suspended ? "active" : "suspended"),
    IDLE,
  );
  return (
    <form
      action={action}
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        if (suspended) return;
        const ok = window.confirm(
          `Suspend ${name}? Its members are locked out, its data is hidden and its incoming email and WhatsApp are dropped until you reactivate it. Nothing is deleted.`,
        );
        if (!ok) e.preventDefault();
      }}
    >
      <FormStatus state={state} />
      <p className="text-sm">
        {suspended
          ? "Suspended: members cannot open the workspace, and incoming messages are dropped."
          : "Active: members can use the workspace."}
      </p>
      <Button
        type="submit"
        variant={suspended ? "default" : "destructive"}
        disabled={pending}
        className="self-start"
      >
        {suspended ? "Reactivate" : "Suspend organisation"}
      </Button>
    </form>
  );
}

export function NewInvitationForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState<AdminFormState, FormData>(
    issueInvitation.bind(null, slug),
    IDLE,
  );
  return (
    <form action={action} className="flex max-w-lg flex-col gap-3" noValidate>
      <FormStatus state={state} />
      {state.inviteLink ? <CopyLink link={state.inviteLink} label="One-time link" /> : null}
      <div className="flex flex-wrap items-end gap-3">
        <FormField
          id="admin-invite-email"
          label="Email"
          error={state.fieldErrors?.email}
          className="min-w-64 flex-1"
        >
          <Input id="admin-invite-email" name="email" type="email" required autoComplete="off" />
        </FormField>
        <FormField id="admin-invite-role" label="Role" className="w-36">
          <select id="admin-invite-role" name="role" defaultValue="owner" className={SELECT_CLASS}>
            <option value="owner">Owner</option>
            <option value="admin">Admin</option>
            <option value="member">Member</option>
          </select>
        </FormField>
        <Button type="submit" variant="outline" disabled={pending}>
          {pending ? "Creating…" : "Create link"}
        </Button>
      </div>
    </form>
  );
}

export function InvitationRow({
  slug,
  invitation,
  created,
}: {
  slug: string;
  invitation: AdminInvitation;
  created: string;
}) {
  const [state, action, pending] = useActionState(
    revokeInvitation.bind(null, slug, invitation.id),
    IDLE,
  );
  return (
    <li className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center">
      <div className="flex flex-1 flex-col gap-1">
        <span className="font-medium break-all">
          {invitation.email} <span className="text-muted-foreground">({invitation.role})</span>
        </span>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={INVITATION_STATE_VARIANT[invitation.state]}>
            {INVITATION_STATE_LABEL[invitation.state]}
          </Badge>
          <span className="text-muted-foreground">Created {created}</span>
        </span>
        <FormStatus state={state} />
      </div>
      {invitation.state === "pending" ? (
        <form action={action}>
          <Button
            type="submit"
            variant="outline"
            size="sm"
            disabled={pending}
            aria-label={`Revoke the invitation for ${invitation.email}`}
          >
            Revoke
          </Button>
        </form>
      ) : null}
    </li>
  );
}

export function BudgetForm({
  slug,
  limitMicros,
  alertPercent,
}: {
  slug: string;
  limitMicros: number | null;
  alertPercent: number | null;
}) {
  const [state, action, pending] = useActionState(setAIBudget.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex flex-wrap items-end gap-3" noValidate>
      <FormField
        id="admin-budget"
        label="Monthly limit (USD)"
        error={state.fieldErrors?.monthly_limit_usd_micros}
        className="w-48"
      >
        <Input
          id="admin-budget"
          name="ai_budget"
          type="number"
          min={0}
          step="0.01"
          required
          defaultValue={limitMicros === null ? "" : (limitMicros / 1_000_000).toFixed(2)}
        />
      </FormField>
      <FormField
        id="admin-alert"
        label="Alert at (%)"
        error={state.fieldErrors?.alert_percent}
        className="w-32"
      >
        <Input
          id="admin-alert"
          name="alert_percent"
          type="number"
          min={1}
          max={100}
          defaultValue={alertPercent ?? 80}
        />
      </FormField>
      <Button type="submit" variant="outline" disabled={pending}>
        Save budget
      </Button>
      <div className="w-full">
        <FormStatus state={state} />
      </div>
    </form>
  );
}
