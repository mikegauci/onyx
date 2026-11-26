"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass, textareaClass } from "@onyx/ui/lib/form-classes";
import Link from "next/link";
import { useActionState, useState } from "react";

import { crmPath, formatInZone } from "@/lib/crm";
import { dealsPath } from "@/lib/deals";
import { IDLE } from "@/lib/form-state";
import {
  REVIEW_PARAM_LABEL,
  REVIEW_STATUS_LABEL,
  REVIEW_STATUS_VARIANT,
  type ReviewRequest,
  type ReviewSettings,
  reviewSkipReason,
} from "@/lib/reviews";

import { FormStatus } from "../../../settings/form-status";
import { dismissReviewRequest, saveReviewSettings, sendReviewRequests } from "../review-actions";

function DismissRequest({ slug, id }: { slug: string; id: string }) {
  const [, action, pending] = useActionState(dismissReviewRequest.bind(null, slug, id), IDLE);
  return (
    <form action={action}>
      <Button type="submit" variant="ghost" size="sm" disabled={pending}>
        Dismiss
      </Button>
    </form>
  );
}

export function ReviewRequestList({
  slug,
  items,
  canSend,
  canWrite,
  timezone,
}: {
  slug: string;
  items: ReviewRequest[];
  canSend: boolean;
  canWrite: boolean;
  timezone: string;
}) {
  const [state, action, pending] = useActionState(sendReviewRequests.bind(null, slug), IDLE);
  const sendable = (r: ReviewRequest) => r.status === "pending" || r.status === "skipped";
  const formId = "send-review-requests";
  return (
    <div className="flex flex-col gap-3">
      <FormStatus state={state} />
      <form id={formId} action={action} className="contents" />
      <ul className="divide-y rounded-2xl border" aria-label="Review requests">
        {items.map((r) => (
          <li key={r.id} className="flex flex-wrap items-start gap-3 p-4">
            {canSend && sendable(r) ? (
              <input
                type="checkbox"
                name="request_id"
                value={r.id}
                form={formId}
                defaultChecked={r.status === "pending"}
                aria-label={`Send to ${r.contact_name}`}
                className="mt-1"
              />
            ) : null}
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <Link
                  href={crmPath(slug, "contacts", r.contact_id)}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {r.contact_name}
                </Link>
                <span className="text-muted-foreground">collected</span>
                <Link
                  href={dealsPath(slug, r.deal_id)}
                  className="underline-offset-4 hover:underline"
                >
                  {r.deal_title}
                </Link>
                <Badge variant={REVIEW_STATUS_VARIANT[r.status]}>
                  {REVIEW_STATUS_LABEL[r.status]}
                </Badge>
              </p>
              <p className="text-muted-foreground text-xs">
                {r.collected_at ? `Collected ${formatInZone(r.collected_at, timezone)}` : null}
                {r.channel ? ` · sent by ${r.channel === "email" ? "email" : "WhatsApp"}` : null}
                {!r.has_phone && !r.has_email ? " · no phone or email" : null}
              </p>
              {reviewSkipReason(r.skip_reason) ? (
                <p className="text-xs">{reviewSkipReason(r.skip_reason)}</p>
              ) : null}
            </div>
            {canWrite && sendable(r) ? <DismissRequest slug={slug} id={r.id} /> : null}
          </li>
        ))}
      </ul>
      {canSend && items.some(sendable) ? (
        <Button type="submit" form={formId} disabled={pending} className="self-start">
          {pending ? "Sending…" : "Send selected requests"}
        </Button>
      ) : null}
    </div>
  );
}

export function ReviewSettingsForm({
  slug,
  settings,
  templates,
}: {
  slug: string;
  settings: ReviewSettings;
  templates: { id: string; label: string; paramCount: number; body: string | null }[];
}) {
  const [state, action, pending] = useActionState(saveReviewSettings.bind(null, slug), IDLE);
  const [templateId, setTemplateId] = useState(settings.template_id ?? "");
  const chosen = templates.find((t) => t.id === templateId);
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4">
      <FormStatus state={state} />
      <FormField
        id="google_review_url"
        label="Google review link"
        hint="From your Google Business Profile: “Ask for reviews”. Leave empty to turn requests off."
        error={state.fieldErrors?.google_review_url}
      >
        <Input
          id="google_review_url"
          name="google_review_url"
          type="url"
          placeholder="https://g.page/r/…/review"
          defaultValue={settings.google_review_url ?? ""}
        />
      </FormField>
      <FormField
        id="delay_days"
        label="Days after collection"
        hint="Between 1 and 60."
        error={state.fieldErrors?.delay_days}
      >
        <Input
          id="delay_days"
          name="delay_days"
          type="number"
          min={1}
          max={60}
          defaultValue={settings.delay_days}
          className="w-28"
        />
      </FormField>
      <FormField
        id="email_subject"
        label="Email subject"
        hint="{workspace} becomes your business name."
        error={state.fieldErrors?.email_subject}
      >
        <Input
          id="email_subject"
          name="email_subject"
          maxLength={200}
          defaultValue={settings.email_subject}
        />
      </FormField>
      <FormField
        id="message"
        label="Message"
        hint="Used for email, and on WhatsApp within 24 hours of the customer’s last message. {name}, {car} and {link} are filled in."
        error={state.fieldErrors?.message}
      >
        <textarea
          id="message"
          name="message"
          maxLength={1000}
          defaultValue={settings.message}
          className={`${textareaClass} min-h-24`}
        />
      </FormField>
      <FormField
        id="template_id"
        label="WhatsApp template (after 24 hours)"
        hint="An approved utility template. Without one, customers who have not written recently get the email instead."
        error={state.fieldErrors?.template_id}
      >
        <select
          id="template_id"
          name="template_id"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          className={selectClass}
        >
          <option value="">None (use email)</option>
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
                className={selectClass}
              >
                {settings.param_keys.map((k) => (
                  <option key={k} value={k}>
                    {REVIEW_PARAM_LABEL[k] ?? k}
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
