"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import Link from "next/link";
import { useActionState, useState } from "react";

import {
  type AlertSettings,
  type CarMatch,
  type Consent,
  CONSENT_METHOD_LABEL,
  type ConsentMethod,
  MATCH_STATUS_LABEL,
  MATCH_STATUS_VARIANT,
  PARAM_LABEL,
  skipReason,
  type Wanted,
  wantedSummary,
} from "@/lib/alerts";
import { automotivePath, euros } from "@/lib/automotive";
import { crmPath, formatInZone } from "@/lib/crm";
import { IDLE } from "@/lib/form-state";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import {
  confirmWanted,
  dismissMatch,
  grantConsent,
  saveAlertSettings,
  saveWanted,
  sendMatches,
  withdrawConsent,
} from "../alert-actions";

// --- consent (contact page) ------------------------------------------------------------------

const METHODS = Object.keys(CONSENT_METHOD_LABEL) as ConsentMethod[];

export function ConsentPanel({
  slug,
  contactId,
  consent,
  canWrite,
  timezone,
}: {
  slug: string;
  contactId: string;
  consent: Consent;
  canWrite: boolean;
  timezone: string;
}) {
  const [granted, grant, granting] = useActionState(grantConsent.bind(null, slug, contactId), IDLE);
  const [withdrawn, withdraw, withdrawing] = useActionState(
    withdrawConsent.bind(null, slug, contactId),
    IDLE,
  );
  return (
    <div className="flex flex-col gap-4">
      <FormStatus state={withdrawn.status !== "idle" ? withdrawn : granted} />
      <p className="text-sm">
        {consent.active ? (
          <Badge variant="success">Agreed to car alerts</Badge>
        ) : (
          <Badge variant="outline">No consent to car alerts</Badge>
        )}
      </p>
      {canWrite && consent.active ? (
        <form action={withdraw}>
          <Button type="submit" variant="outline" size="sm" disabled={withdrawing}>
            {withdrawing ? "Withdrawing…" : "Withdraw consent"}
          </Button>
        </form>
      ) : null}
      {canWrite && !consent.active ? (
        <form action={grant} className="flex flex-col gap-3" aria-label="Record consent">
          <p className="text-muted-foreground text-sm">
            Only record this when the customer has said they want WhatsApp messages about new cars.
            They can reply STOP at any time.
          </p>
          <FormField id="consent-method" label="How did they agree?">
            <select
              id="consent-method"
              name="method"
              className={SELECT_CLASS}
              defaultValue="in_person"
            >
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {CONSENT_METHOD_LABEL[m]}
                </option>
              ))}
            </select>
          </FormField>
          <FormField id="consent-note" label="Note" hint="Optional, e.g. where or who asked.">
            <Input id="consent-note" name="note" maxLength={300} />
          </FormField>
          <Button type="submit" size="sm" disabled={granting} className="self-start">
            {granting ? "Saving…" : "Record consent"}
          </Button>
        </form>
      ) : null}
      {consent.history.length > 0 ? (
        <ul className="text-muted-foreground flex flex-col gap-1 border-t pt-3 text-xs">
          {consent.history.map((h) => (
            <li key={h.id}>
              Agreed {CONSENT_METHOD_LABEL[h.method].toLowerCase()} on{" "}
              {formatInZone(h.granted_at, timezone)}
              {h.recorded_by ? ` (recorded by ${h.recorded_by})` : ""}
              {h.withdrawn_at
                ? ` · withdrawn ${h.withdrawn_via === "whatsapp_stop" ? "by a STOP reply" : "by staff"} on ${formatInZone(h.withdrawn_at, timezone)}`
                : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// --- wanted criteria (lead page) -------------------------------------------------------------

function WantedForm({ slug, leadId, wanted }: { slug: string; leadId: string; wanted?: Wanted }) {
  const [state, action, pending] = useActionState(
    saveWanted.bind(null, slug, leadId, wanted?.id ?? null),
    IDLE,
  );
  const errors = state.fieldErrors ?? {};
  const key = wanted?.id ?? "new";
  return (
    <form action={action} className="flex flex-col gap-3" noValidate>
      <FormStatus state={state} />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id={`make-${key}`} label="Make" error={errors.make}>
          <Input id={`make-${key}`} name="make" defaultValue={wanted?.make ?? ""} maxLength={100} />
        </FormField>
        <FormField id={`model-${key}`} label="Model" error={errors.model}>
          <Input
            id={`model-${key}`}
            name="model"
            defaultValue={wanted?.model ?? ""}
            maxLength={100}
          />
        </FormField>
        <FormField id={`price-${key}`} label="Maximum price (€)" error={errors.price_max_cents}>
          <Input
            id={`price-${key}`}
            name="price_max"
            inputMode="decimal"
            defaultValue={wanted?.price_max_cents ? String(wanted.price_max_cents / 100) : ""}
          />
        </FormField>
        <FormField id={`year-${key}`} label="From year" error={errors.year_min}>
          <Input
            id={`year-${key}`}
            name="year_min"
            inputMode="numeric"
            defaultValue={wanted?.year_min ?? ""}
          />
        </FormField>
        <FormField id={`km-${key}`} label="Maximum mileage (km)" error={errors.mileage_max_km}>
          <Input
            id={`km-${key}`}
            name="mileage_max_km"
            inputMode="numeric"
            defaultValue={wanted?.mileage_max_km ?? ""}
          />
        </FormField>
        <FormField id={`fuel-${key}`} label="Fuel" error={errors.fuel}>
          <Input id={`fuel-${key}`} name="fuel" defaultValue={wanted?.fuel ?? ""} maxLength={64} />
        </FormField>
      </div>
      {wanted ? (
        <label className="flex items-center gap-2 text-sm">
          <input type="hidden" name="active" value="off" />
          <input type="checkbox" name="active" value="on" defaultChecked={wanted.active} />
          Still looking
        </label>
      ) : null}
      <Button type="submit" size="sm" disabled={pending} className="self-start">
        {pending ? "Saving…" : wanted ? "Save" : "Add"}
      </Button>
    </form>
  );
}

function ConfirmButton({ slug, wantedId }: { slug: string; wantedId: string }) {
  const [state, action, pending] = useActionState(confirmWanted.bind(null, slug, wantedId), IDLE);
  return (
    <form action={action} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <Button type="submit" size="sm" disabled={pending} className="self-start">
        {pending ? "Confirming…" : "Confirm suggestion"}
      </Button>
    </form>
  );
}

export function WantedPanel({
  slug,
  leadId,
  items,
  canWrite,
}: {
  slug: string;
  leadId: string;
  items: Wanted[];
  canWrite: boolean;
}) {
  const [adding, setAdding] = useState(items.length === 0);
  return (
    <div className="flex flex-col gap-5">
      {items.map((w) => (
        <details key={w.id} className="flex flex-col gap-3 border-b pb-4 last:border-b-0">
          <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{wantedSummary(w) || "Any car"}</span>
            {!w.active ? <Badge variant="outline">Stopped</Badge> : null}
            {!w.confirmed ? <Badge variant="warning">Suggested by the assistant</Badge> : null}
            {w.pending_matches > 0 ? (
              <Link
                className="text-brand text-xs underline-offset-4 hover:underline"
                href={`${automotivePath(slug, "matches")}?lead_id=${w.lead_id}`}
              >
                {w.pending_matches} match{w.pending_matches === 1 ? "" : "es"} to send
              </Link>
            ) : null}
          </summary>
          <div className="mt-3 flex flex-col gap-3">
            {canWrite && !w.confirmed ? <ConfirmButton slug={slug} wantedId={w.id} /> : null}
            {canWrite ? <WantedForm slug={slug} leadId={leadId} wanted={w} /> : null}
          </div>
        </details>
      ))}
      {items.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          Nothing recorded. Add what the buyer is looking for, and Onyx lists matching cars as they
          arrive.
        </p>
      ) : null}
      {canWrite ? (
        adding ? (
          <WantedForm slug={slug} leadId={leadId} />
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => setAdding(true)}
          >
            Add another
          </Button>
        )
      ) : null}
    </div>
  );
}

// --- matches ---------------------------------------------------------------------------------

function DismissButton({ slug, matchId }: { slug: string; matchId: string }) {
  const [, action, pending] = useActionState(dismissMatch.bind(null, slug, matchId), IDLE);
  return (
    <form action={action}>
      <Button type="submit" variant="ghost" size="sm" disabled={pending}>
        Dismiss
      </Button>
    </form>
  );
}

export function MatchList({
  slug,
  items,
  canSend,
  canWrite,
  showCar = true,
}: {
  slug: string;
  items: CarMatch[];
  canSend: boolean;
  canWrite: boolean;
  showCar?: boolean;
}) {
  const [state, action, pending] = useActionState(sendMatches.bind(null, slug), IDLE);
  const sendable = (m: CarMatch) => m.status === "pending" || m.status === "skipped";
  const formId = "send-matches";
  return (
    <div className="flex flex-col gap-3">
      <FormStatus state={state} />
      <form id={formId} action={action} className="contents" />
      <ul className="divide-y rounded-2xl border" aria-label="Matches">
        {items.map((m) => (
          <li key={m.id} className="flex flex-wrap items-start gap-3 p-4">
            {canSend && sendable(m) ? (
              <input
                type="checkbox"
                name="match_id"
                value={m.id}
                form={formId}
                defaultChecked={m.status === "pending" && m.contact.consented}
                aria-label={`Send to ${m.contact.full_name}`}
                className="mt-1"
              />
            ) : null}
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <Link
                  href={crmPath(slug, "leads", m.lead_id)}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {m.contact.full_name}
                </Link>
                {showCar ? (
                  <>
                    <span className="text-muted-foreground">·</span>
                    <Link
                      href={automotivePath(slug, "vehicles", m.vehicle.id)}
                      className="underline-offset-4 hover:underline"
                    >
                      {m.vehicle.title}
                    </Link>
                    <span className="text-muted-foreground tabular-nums">
                      {euros(m.vehicle.price_cents)}
                    </span>
                  </>
                ) : null}
                <Badge variant={MATCH_STATUS_VARIANT[m.status]}>
                  {MATCH_STATUS_LABEL[m.status]}
                </Badge>
                {m.contact.consented ? null : <Badge variant="outline">No consent</Badge>}
              </p>
              <p className="text-muted-foreground text-xs">{m.reasons.join(" · ")}</p>
              {skipReason(m.skip_reason) ? (
                <p className="text-xs">{skipReason(m.skip_reason)}</p>
              ) : null}
            </div>
            {canWrite && sendable(m) ? <DismissButton slug={slug} matchId={m.id} /> : null}
          </li>
        ))}
      </ul>
      {canSend && items.some(sendable) ? (
        <Button type="submit" form={formId} disabled={pending} className="self-start">
          {pending ? "Sending…" : "Send selected alerts"}
        </Button>
      ) : null}
    </div>
  );
}

// --- settings --------------------------------------------------------------------------------

export function AlertSettingsForm({
  slug,
  settings,
  templates,
}: {
  slug: string;
  settings: AlertSettings;
  templates: { id: string; label: string; paramCount: number; body: string | null }[];
}) {
  const [state, action, pending] = useActionState(saveAlertSettings.bind(null, slug), IDLE);
  const [templateId, setTemplateId] = useState(settings.template_id ?? "");
  const chosen = templates.find((t) => t.id === templateId);
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4">
      <FormStatus state={state} />
      <FormField
        id="template_id"
        label="WhatsApp template"
        hint="An approved marketing template from WhatsApp Manager. Sync templates in Inbox first."
        error={state.fieldErrors?.template_id}
      >
        <select
          id="template_id"
          name="template_id"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Off (no car alerts)</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </FormField>
      {chosen?.body ? (
        <p className="bg-muted rounded-xl px-4 py-3 text-sm whitespace-pre-wrap">{chosen.body}</p>
      ) : null}
      {chosen
        ? Array.from({ length: chosen.paramCount }, (_, i) => (
            <FormField key={i} id={`param-${i}`} label={`Value {{${i + 1}}}`}>
              <select
                id={`param-${i}`}
                name="param"
                defaultValue={settings.params[i] ?? settings.param_keys[i] ?? "first_name"}
                className={SELECT_CLASS}
              >
                {settings.param_keys.map((k) => (
                  <option key={k} value={k}>
                    {PARAM_LABEL[k] ?? k}
                  </option>
                ))}
              </select>
            </FormField>
          ))
        : null}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
