"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass, textareaClass } from "@onyx/ui/lib/form-classes";
import { Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useActionState, useRef, useState, useTransition } from "react";

import { euros } from "@/lib/automotive";
import {
  APPLICANT_LABEL,
  type ApplicantType,
  type ApplicationStatus,
  type Estimate,
  type FinanceSettings,
  MARITAL_LABEL,
  type MaritalStatus,
  percent,
  STATUS_LABEL,
  termLabel,
} from "@/lib/finance";
import { type FormState, IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import {
  calculate,
  changeApplicationStatus,
  createApplication,
  type EstimateState,
  saveFinanceSettings,
  uploadFinanceForm,
} from "../finance-actions";

export function EstimateBreakdown({ estimate }: { estimate: Estimate }) {
  const rows: [string, string][] = [
    ["Vehicle price", euros(estimate.price_cents)],
    ["Deposit", euros(estimate.deposit_cents)],
    ["Net loan", euros(estimate.net_loan_cents)],
    ["Term", `${termLabel(estimate.term_months)} (${estimate.term_months} months)`],
    [`Interest (${percent(estimate.annual_rate_bp)} a year)`, euros(estimate.interest_cents)],
    [
      `Financing & maintenance fee (${percent(estimate.yearly_fee_bp)} a year)`,
      euros(estimate.yearly_fee_cents),
    ],
    [
      `Onboarding fee (${percent(estimate.onboarding_fee_bp)})`,
      euros(estimate.onboarding_fee_cents),
    ],
    ["Total", euros(estimate.total_cents)],
  ];
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      <p className="text-sm">
        Estimated monthly payment{" "}
        <strong className="block text-3xl font-semibold tracking-tight tabular-nums">
          {euros(estimate.monthly_cents)}
        </strong>
      </p>
      <dl className="divide-y text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-1.5">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-medium tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      {estimate.payoff_saving_cents !== null && estimate.payoff_months ? (
        <p className="text-sm">
          Paying off after {termLabel(estimate.payoff_months)} saves about{" "}
          <strong>{euros(estimate.payoff_saving_cents)}</strong>.
        </p>
      ) : null}
      <p className="text-muted-foreground text-xs">{estimate.disclaimer}</p>
    </div>
  );
}

export function Calculator({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState<EstimateState, FormData>(
    calculate.bind(null, slug),
    IDLE,
  );
  const errors = state.fieldErrors ?? {};
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <form
        action={action}
        className="flex flex-col gap-3"
        noValidate
        aria-label="Finance estimate"
      >
        {state.status === "error" ? <FormStatus state={state} /> : null}
        <FormField
          id="calc-price"
          label="Vehicle price (€)"
          error={errors.price ?? errors.price_cents}
        >
          <Input id="calc-price" name="price" inputMode="decimal" />
        </FormField>
        <FormField
          id="calc-deposit"
          label="Deposit (€)"
          error={errors.deposit ?? errors.deposit_cents}
        >
          <Input id="calc-deposit" name="deposit" inputMode="decimal" />
        </FormField>
        <FormField
          id="calc-years"
          label="Years"
          hint="In halves, e.g. 5 or 3.5."
          error={errors.years ?? errors.term_months}
        >
          <Input id="calc-years" name="years" inputMode="decimal" />
        </FormField>
        <FormField
          id="calc-payoff"
          label="Pay off after (years, optional)"
          error={errors.payoff_years}
        >
          <Input id="calc-payoff" name="payoff_years" inputMode="decimal" />
        </FormField>
        <Button type="submit" disabled={pending} className="self-start">
          {pending ? "Working out…" : "Work out the estimate"}
        </Button>
      </form>
      <div>
        {state.estimate ? (
          <EstimateBreakdown estimate={state.estimate} />
        ) : (
          <p className="text-muted-foreground text-sm">
            The same calculation as your website&apos;s loan calculator.
          </p>
        )}
      </div>
    </div>
  );
}

type Option = { id: string; label: string };

export function NewApplicationForm({
  slug,
  contacts,
  dealId,
  canManage,
}: {
  slug: string;
  contacts: Option[];
  dealId: string;
  canManage: boolean;
}) {
  const [state, action, pending] = useActionState(createApplication.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <input type="hidden" name="deal_id" value={dealId} />
      {dealId ? (
        <p className="text-muted-foreground text-sm">
          For the deal: the customer comes from the deal.
        </p>
      ) : (
        <FormField id="fin-contact" label="Customer" error={errors.contact_id}>
          <select id="fin-contact" name="contact_id" className={selectClass} defaultValue="">
            <option value="">Choose a contact</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </FormField>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="fin-type" label="Applicant type" error={errors.applicant_type}>
          <select
            id="fin-type"
            name="applicant_type"
            className={selectClass}
            defaultValue="maltese_resident"
          >
            {(Object.keys(APPLICANT_LABEL) as ApplicantType[]).map((t) => (
              <option key={t} value={t}>
                {APPLICANT_LABEL[t]}
              </option>
            ))}
          </select>
        </FormField>
        <FormField
          id="fin-marital"
          label="Marital status"
          hint="Married applicants also need their spouse's documents."
          error={errors.marital_status}
        >
          <select
            id="fin-marital"
            name="marital_status"
            className={selectClass}
            defaultValue="single"
          >
            {(Object.keys(MARITAL_LABEL) as MaritalStatus[]).map((m) => (
              <option key={m} value={m}>
                {MARITAL_LABEL[m]}
              </option>
            ))}
          </select>
        </FormField>
      </div>
      <FormField id="fin-vehicle" label="Vehicle (optional)" error={errors.vehicle_label}>
        <Input id="fin-vehicle" name="vehicle_label" maxLength={300} />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField id="fin-price" label="Price (€)" error={errors.price ?? errors.price_cents}>
          <Input id="fin-price" name="price" inputMode="decimal" />
        </FormField>
        <FormField
          id="fin-deposit"
          label="Deposit (€)"
          error={errors.deposit ?? errors.deposit_cents}
        >
          <Input id="fin-deposit" name="deposit" inputMode="decimal" />
        </FormField>
        <FormField id="fin-years" label="Years" error={errors.years ?? errors.term_months}>
          <Input id="fin-years" name="years" inputMode="decimal" />
        </FormField>
      </div>
      {canManage ? (
        <fieldset className="flex flex-col gap-4 rounded-xl border p-4">
          <legend className="px-1 text-sm font-medium">Income (owners and admins only)</legend>
          <FormField id="fin-employer" label="Employer" error={errors.employer}>
            <Input id="fin-employer" name="employer" maxLength={200} />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="fin-income" label="Net monthly income (€)" error={errors.income}>
              <Input id="fin-income" name="income" inputMode="decimal" />
            </FormField>
            <FormField
              id="fin-commitments"
              label="Existing monthly commitments (€)"
              error={errors.commitments}
            >
              <Input id="fin-commitments" name="commitments" inputMode="decimal" />
            </FormField>
          </div>
          <FormField id="fin-notes" label="Notes" error={errors.notes}>
            <textarea id="fin-notes" name="notes" rows={3} className={textareaClass} />
          </FormField>
        </fieldset>
      ) : null}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Start finance application"}
      </Button>
    </form>
  );
}

const MEMBER_MOVES: ApplicationStatus[] = ["started", "documents", "in_review", "withdrawn"];

export function StatusForm({
  slug,
  id,
  current,
  canManage,
}: {
  slug: string;
  id: string;
  current: ApplicationStatus;
  canManage: boolean;
}) {
  const [state, action, pending] = useActionState(
    changeApplicationStatus.bind(null, slug, id),
    IDLE,
  );
  const closed = ["approved", "declined", "withdrawn"].includes(current);
  const options = (canManage ? [...MEMBER_MOVES, "approved", "declined"] : MEMBER_MOVES).filter(
    (s) => s !== current,
  ) as ApplicationStatus[];
  if (closed && !canManage) {
    return <p className="text-muted-foreground text-sm">This application is closed.</p>;
  }
  return (
    <form
      action={action}
      className="flex flex-col gap-3"
      noValidate
      aria-label="Application status"
    >
      <FormStatus state={state} />
      <FormField id="fin-status" label="Move to">
        <select id="fin-status" name="status" className={selectClass} defaultValue={options[0]}>
          {options.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </FormField>
      {canManage ? (
        <FormField
          id="fin-note"
          label="Decision note (optional)"
          hint="Kept with the decision; staff without finance access don't see it."
        >
          <Input id="fin-note" name="note" maxLength={500} />
        </FormField>
      ) : null}
      <Button type="submit" variant="secondary" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Update"}
      </Button>
    </form>
  );
}

export function FinanceSettingsForm({
  slug,
  settings,
}: {
  slug: string;
  settings: FinanceSettings;
}) {
  const [state, action, pending] = useActionState(saveFinanceSettings.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  const pct = (bp: number) => String(bp / 100);
  return (
    <form action={action} className="flex flex-col gap-4" noValidate aria-label="Finance settings">
      <FormStatus state={state} />
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField id="fs-rate" label="Interest (% a year)" error={errors.annual_rate_bp}>
          <Input
            id="fs-rate"
            name="annual_rate_bp"
            defaultValue={pct(settings.annual_rate_bp)}
            inputMode="decimal"
          />
        </FormField>
        <FormField id="fs-onboarding" label="Onboarding fee (%)" error={errors.onboarding_fee_bp}>
          <Input
            id="fs-onboarding"
            name="onboarding_fee_bp"
            defaultValue={pct(settings.onboarding_fee_bp)}
            inputMode="decimal"
          />
        </FormField>
        <FormField
          id="fs-yearly"
          label="Financing & maintenance fee (% a year)"
          error={errors.yearly_fee_bp}
        >
          <Input
            id="fs-yearly"
            name="yearly_fee_bp"
            defaultValue={pct(settings.yearly_fee_bp)}
            inputMode="decimal"
          />
        </FormField>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="fs-min" label="Shortest term (years)" error={errors.min_years}>
          <Input
            id="fs-min"
            name="min_years"
            defaultValue={String(settings.min_term_months / 12)}
            inputMode="decimal"
          />
        </FormField>
        <FormField id="fs-max" label="Longest term (years)" error={errors.max_years}>
          <Input
            id="fs-max"
            name="max_years"
            defaultValue={String(settings.max_term_months / 12)}
            inputMode="decimal"
          />
        </FormField>
      </div>
      <FormField
        id="fs-disclaimer"
        label="Disclaimer shown with every estimate"
        error={errors.disclaimer}
      >
        <textarea
          id="fs-disclaimer"
          name="disclaimer"
          rows={2}
          maxLength={500}
          defaultValue={settings.disclaimer}
          className={textareaClass}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save finance settings"}
      </Button>
    </form>
  );
}

async function toBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export function FormUpload({
  slug,
  kind,
  label,
  uploaded,
  downloadHref,
}: {
  slug: string;
  kind: "kyc" | "ccr";
  label: string;
  uploaded: boolean;
  downloadHref: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [state, setState] = useState<FormState>(IDLE);
  const [pending, start] = useTransition();
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border p-3 text-sm">
      <span className="font-medium">{label}</span>
      {uploaded ? (
        <a className="text-brand underline-offset-4 hover:underline" href={downloadHref}>
          Download current
        </a>
      ) : (
        <span className="text-muted-foreground">Not uploaded yet</span>
      )}
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        className="sr-only"
        aria-label={`Upload ${label} (PDF)`}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          start(async () => {
            if (file.size > 3 * 1024 * 1024) {
              setState({ status: "error", message: "The PDF is over 3 MB." });
              return;
            }
            const result = await uploadFinanceForm(slug, kind, {
              filename: file.name.slice(0, 255),
              content_base64: await toBase64(file),
            });
            setState(result);
            if (result.status === "ok") router.refresh();
          });
        }}
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={pending}
        onClick={() => input.current?.click()}
        className="ml-auto"
      >
        <Upload aria-hidden />
        {pending ? "Uploading…" : uploaded ? "Replace PDF" : "Upload PDF"}
      </Button>
      {state.status !== "idle" ? (
        <div className="w-full">
          <FormStatus state={state} />
        </div>
      ) : null}
    </div>
  );
}
