"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { textareaClass } from "@onyx/ui/lib/form-classes";
import Link from "next/link";
import { useActionState, useState } from "react";

import { formatInZone } from "@/lib/crm";
import { IDLE } from "@/lib/form-state";
import { previewTemplate, type WhatsAppTemplate } from "@/lib/inbox";
import {
  type DraftDetail,
  DRAFT_STATUS_LABEL,
  DRAFT_STATUS_VARIANT,
  draftControls,
  isEdited,
  originLabel,
  outboundPath,
  revisionAuthor,
} from "@/lib/outbound";
import { quotationsPath } from "@/lib/quotations";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import {
  approveAndSendDraft,
  approveDraft,
  createDraft,
  rejectDraft,
  reviseDraft,
  sendDraft,
  updateExpiry,
} from "../actions";

const TEXTAREA_CLASS = `${textareaClass} min-h-32`;

type QuoteOption = { id: string; label: string };

/** What the reply panel knows about a WhatsApp conversation. */
export type WhatsAppReply = { windowOpen: boolean; templates: WhatsAppTemplate[] };

/** Write a reply for approval, optionally with one of the contact's quotes. */
export function NewDraftForm({
  slug,
  conversationId,
  quotes,
  whatsapp = null,
}: {
  slug: string;
  conversationId: string;
  quotes: QuoteOption[];
  whatsapp?: WhatsAppReply | null;
}) {
  const [state, action, pending] = useActionState(
    createDraft.bind(null, slug, conversationId),
    IDLE,
  );
  const errors = state.fieldErrors ?? {};
  const [mode, setMode] = useState<"text" | "template">(
    whatsapp && !whatsapp.windowOpen ? "template" : "text",
  );
  const usable = whatsapp?.templates.filter((t) => t.usable) ?? [];
  return (
    <form action={action} className="flex flex-col gap-3" noValidate>
      <input type="hidden" name="mode" value={mode} />
      {whatsapp ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">Reply as</legend>
          <div className="bg-foreground/[0.03] flex flex-wrap gap-1 self-start rounded-full border p-1">
            <label className="text-muted-foreground has-[:checked]:bg-foreground/10 has-[:checked]:text-foreground has-[:focus-visible]:ring-ring flex cursor-pointer items-center rounded-full px-3 py-1.5 text-xs font-medium transition-colors has-[:disabled]:opacity-50 has-[:focus-visible]:ring-2">
              <input
                className="sr-only"
                type="radio"
                name="reply-mode"
                checked={mode === "text"}
                disabled={!whatsapp.windowOpen}
                onChange={() => setMode("text")}
              />
              Text message
            </label>
            <label className="text-muted-foreground has-[:checked]:bg-foreground/10 has-[:checked]:text-foreground has-[:focus-visible]:ring-ring flex cursor-pointer items-center rounded-full px-3 py-1.5 text-xs font-medium transition-colors has-[:disabled]:opacity-50 has-[:focus-visible]:ring-2">
              <input
                className="sr-only"
                type="radio"
                name="reply-mode"
                checked={mode === "template"}
                onChange={() => setMode("template")}
              />
              Approved template
            </label>
          </div>
          {!whatsapp.windowOpen ? (
            <p className="text-muted-foreground text-xs">
              The 24-hour window is closed, so only a template can be sent.
            </p>
          ) : null}
        </fieldset>
      ) : null}
      {mode === "text" ? (
        <FormField id="draft-body" label="Reply to the customer" error={errors.body}>
          <textarea
            id="draft-body"
            name="body"
            required
            maxLength={10000}
            className={TEXTAREA_CLASS}
          />
        </FormField>
      ) : usable.length === 0 ? (
        <p
          role="note"
          className="border-warning/30 bg-warning/[0.07] rounded-lg border px-3 py-2 text-sm"
        >
          No template can be sent yet. An admin refreshes the approved utility templates under Inbox
          → Channels.
        </p>
      ) : (
        <TemplateFields templates={usable} errors={errors} />
      )}
      {quotes.length > 0 && mode === "text" ? (
        <FormField id="draft-quote" label="Include quote" error={errors.quote_id}>
          <select id="draft-quote" name="quote_id" className={SELECT_CLASS} defaultValue="">
            <option value="">No quote</option>
            {quotes.map((q) => (
              <option key={q.id} value={q.id}>
                {q.label}
              </option>
            ))}
          </select>
        </FormField>
      ) : null}
      <Button type="submit" disabled={pending || (mode === "template" && usable.length === 0)}>
        {pending ? "Saving…" : "Save for approval"}
      </Button>
      <FormStatus state={state} />
    </form>
  );
}

/**
 * Pick a template and fill in its values, with a preview. The API renders the text that is
 * approved and sent, and checks every value.
 */
function TemplateFields({
  templates,
  errors,
  fixed = null,
  initial = [],
  idPrefix = "draft",
}: {
  templates: WhatsAppTemplate[];
  errors: Record<string, string | undefined>;
  /** A draft's template, which a revision keeps; only its values change. */
  fixed?: { id: string; name: string; language: string; count: number; body: string } | null;
  initial?: readonly string[];
  idPrefix?: string;
}) {
  const [templateId, setTemplateId] = useState(fixed?.id ?? templates[0]?.id ?? "");
  const chosen = templates.find((t) => t.id === templateId);
  const count = fixed?.count ?? chosen?.param_count ?? 0;
  const body = fixed?.body ?? chosen?.body ?? "";
  const [values, setValues] = useState<string[]>(() =>
    Array.from({ length: 20 }, (_, i) => initial[i] ?? ""),
  );
  const error = errors["template_id"] ?? errors["template"] ?? errors["params"];
  return (
    <div className="flex flex-col gap-3">
      {fixed ? (
        <>
          <input type="hidden" name="template_id" value={fixed.id} />
          <p className="text-sm">
            Template {fixed.name} ({fixed.language})
          </p>
        </>
      ) : (
        <FormField id={`${idPrefix}-template`} label="Template" error={error}>
          <select
            id={`${idPrefix}-template`}
            name="template_id"
            className={SELECT_CLASS}
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.language})
              </option>
            ))}
          </select>
        </FormField>
      )}
      {Array.from({ length: count }, (_, i) => (
        <FormField
          key={`${templateId}-${i}`}
          id={`${idPrefix}-param-${i + 1}`}
          label={`Value {{${i + 1}}}`}
          hint={i === 0 ? "One line each, as the customer should read it." : undefined}
          error={errors[`params.${i}`]}
        >
          <Input
            id={`${idPrefix}-param-${i + 1}`}
            name="param"
            required
            maxLength={1024}
            value={values[i] ?? ""}
            onChange={(e) =>
              setValues((current) => current.map((v, j) => (j === i ? e.target.value : v)))
            }
          />
        </FormField>
      ))}
      {body ? (
        <div className="flex flex-col gap-1">
          <p className="text-muted-foreground text-xs">Preview</p>
          <blockquote
            className="bg-background rounded-xl border p-3 text-sm whitespace-pre-wrap"
            aria-label="Template preview"
          >
            {previewTemplate(body, values.slice(0, count))}
          </blockquote>
        </div>
      ) : null}
    </div>
  );
}

function QuoteLine({ slug, draft }: { slug: string; draft: DraftDetail }) {
  if (!draft.quote) return null;
  const quote = draft.quote;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>
        With quote{" "}
        <Link
          className="text-brand underline-offset-4 hover:underline"
          href={quotationsPath(slug, "quotes", quote.id)}
        >
          {quote.number}
        </Link>{" "}
        (version {quote.approved_version ?? quote.version}, {quote.status})
      </p>
      {quote.blocked ? (
        <p className="text-warning bg-warning/15 rounded-md px-2 py-1 text-xs">
          {quote.blocked.message}
        </p>
      ) : null}
    </div>
  );
}

/**
 * One draft and what the viewer may do with it. The buttons follow the API's rules for
 * convenience; every request is checked again by the API.
 */
export function DraftCard({
  slug,
  draft,
  permissions,
  timezone,
  showConversation = false,
}: {
  slug: string;
  draft: DraftDetail;
  permissions: readonly string[];
  timezone: string;
  showConversation?: boolean;
}) {
  const controls = draftControls(draft, permissions);
  const [text, setText] = useState(draft.body);
  const edited = isEdited(draft.body, text);

  const [reviseState, revise, revising] = useActionState(
    reviseDraft.bind(null, slug, draft.id, draft.current_revision),
    IDLE,
  );
  const [approveState, approve, approving] = useActionState(
    approveDraft.bind(null, slug, draft.id, draft.current_revision, draft.body),
    IDLE,
  );
  const [rejectState, reject, rejecting] = useActionState(
    rejectDraft.bind(null, slug, draft.id),
    IDLE,
  );
  const [sendState, send, sending] = useActionState(sendDraft.bind(null, slug, draft.id), IDLE);
  const [bothState, approveAndSend, both] = useActionState(
    approveAndSendDraft.bind(null, slug, draft.id, draft.current_revision, draft.body),
    IDLE,
  );
  const busy = revising || approving || rejecting || sending || both;
  const template = draft.template ?? null;
  // A template draft is revised by its values, never edited as text.
  const editable = template === null && (controls.canEdit || controls.canApprove);

  return (
    <article
      className="flex flex-col gap-3"
      aria-label={`Reply: ${DRAFT_STATUS_LABEL[draft.status]}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={DRAFT_STATUS_VARIANT[draft.status]}>
          {DRAFT_STATUS_LABEL[draft.status]}
        </Badge>
        <span className="text-muted-foreground text-xs">
          {originLabel(draft)} · revision {draft.current_revision}
        </span>
      </div>
      {showConversation ? (
        <Link
          className="text-brand text-sm underline-offset-4 hover:underline"
          href={`/w/${encodeURIComponent(slug)}/m/inbox/conversations/${draft.conversation_id}`}
        >
          Conversation: {draft.conversation_subject}
        </Link>
      ) : null}
      {draft.expiry ? (
        <p
          role="note"
          className="border-warning/30 bg-warning/[0.07] rounded-lg border px-3 py-2 text-sm"
        >
          {draft.expiry.message}
        </p>
      ) : null}
      {draft.status === "rejected" && draft.rejection_reason ? (
        <p className="text-sm">
          Rejected by {draft.decided_by?.label ?? "a reviewer"}: {draft.rejection_reason}
        </p>
      ) : null}
      <QuoteLine slug={slug} draft={draft} />
      {template ? (
        <p className="text-muted-foreground text-xs">
          WhatsApp template {template.name} ({template.language}). Approving it approves this exact
          text.
        </p>
      ) : null}

      {editable ? (
        <FormField id={`reply-${draft.id}`} label="Reply text">
          <textarea
            id={`reply-${draft.id}`}
            name="body"
            form={`revise-${draft.id}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={10000}
            className={TEXTAREA_CLASS}
          />
        </FormField>
      ) : (
        <blockquote className="border-brand/25 bg-brand/[0.07] rounded-2xl rounded-tr-md border px-4 py-3 text-sm whitespace-pre-wrap">
          {draft.body}
        </blockquote>
      )}

      <div className="flex flex-wrap gap-2">
        {controls.canEdit && template === null ? (
          <form id={`revise-${draft.id}`} action={revise}>
            <Button type="submit" variant="outline" disabled={busy || !edited}>
              Save edit
            </Button>
          </form>
        ) : null}
        {controls.canApprove ? (
          <form action={approve}>
            <input type="hidden" name="body" value={text} />
            <Button type="submit" disabled={busy || (draft.status === "approved" && !edited)}>
              {edited ? "Approve edited text" : "Approve reply"}
            </Button>
          </form>
        ) : null}
        {controls.canApproveAndSend && (draft.status === "pending" || edited) ? (
          <form action={approveAndSend}>
            <input type="hidden" name="body" value={text} />
            <Button type="submit" variant="secondary" disabled={busy}>
              {both ? "Sending…" : edited ? "Approve edit and send" : "Approve and send"}
            </Button>
          </form>
        ) : null}
        {controls.canSend ? (
          <form action={send}>
            <Button type="submit" disabled={busy || edited}>
              {sending ? "Sending…" : "Send reply"}
            </Button>
          </form>
        ) : null}
      </div>
      {controls.sendHint ? (
        <p className="text-muted-foreground text-xs">{controls.sendHint}</p>
      ) : null}
      {controls.canSend && edited ? (
        <p className="text-muted-foreground text-xs">
          Save or approve the edit first: only the approved text is sent.
        </p>
      ) : null}
      {draft.status === "sent" && draft.sent_at ? (
        <p className="text-sm">
          Sent by {draft.sent_by?.label ?? "a former member"} on{" "}
          <time dateTime={draft.sent_at}>{formatInZone(draft.sent_at, timezone)}</time>
        </p>
      ) : null}
      {draft.approved_by && draft.approved_at && draft.status !== "pending" ? (
        <p className="text-muted-foreground text-xs">
          Revision {draft.approved_revision} approved by {draft.approved_by.label} on{" "}
          <time dateTime={draft.approved_at}>{formatInZone(draft.approved_at, timezone)}</time>
        </p>
      ) : null}

      {controls.canEdit && template ? (
        <details>
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-sm">
            Change the values
          </summary>
          <form action={revise} className="mt-2 flex flex-col gap-2">
            <input type="hidden" name="mode" value="template" />
            <TemplateFields
              templates={[]}
              errors={reviseState.fieldErrors ?? {}}
              fixed={{
                id: template.template_id,
                name: template.name,
                language: template.language,
                count: template.params.length,
                body: "",
              }}
              initial={template.params}
              idPrefix={`revise-${draft.id}`}
            />
            <Button type="submit" variant="outline" disabled={busy}>
              Save new values
            </Button>
          </form>
        </details>
      ) : null}
      <FormStatus state={reviseState} />
      <FormStatus state={approveState} />
      <FormStatus state={sendState} />
      <FormStatus state={bothState} />

      {controls.canReject ? (
        <details>
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-sm">
            Reject this reply
          </summary>
          <form action={reject} className="mt-2 flex flex-col gap-2">
            <FormField
              id={`reject-${draft.id}`}
              label="Reason"
              error={rejectState.fieldErrors?.reason}
            >
              <Input id={`reject-${draft.id}`} name="reason" required maxLength={500} />
            </FormField>
            <Button type="submit" variant="destructive" disabled={busy}>
              Reject reply
            </Button>
            <FormStatus state={rejectState} />
          </form>
        </details>
      ) : null}

      {draft.revisions.length > 1 ? (
        <details>
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-sm">
            All revisions ({draft.revisions.length})
          </summary>
          <ol className="mt-2 flex flex-col gap-2" aria-label="Revisions">
            {draft.revisions.map((revision) => (
              <li key={revision.revision} className="border-foreground/15 border-l-2 pl-3 text-sm">
                <p className="text-muted-foreground text-xs">
                  Revision {revision.revision} by {revisionAuthor(revision)} ·{" "}
                  <time dateTime={revision.created_at}>
                    {formatInZone(revision.created_at, timezone)}
                  </time>
                </p>
                <p className="whitespace-pre-wrap">{revision.body}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
      {!showConversation ? (
        <Link
          className="text-muted-foreground hover:text-foreground text-xs underline-offset-4 hover:underline"
          href={outboundPath(slug, "drafts", draft.id)}
        >
          Open the draft page
        </Link>
      ) : null}
    </article>
  );
}

export function ExpiryForm({
  slug,
  settings,
}: {
  slug: string;
  settings: { expiry_hours: number; remind_after_hours: number; escalate_after_hours: number };
}) {
  const [state, action, pending] = useActionState(updateExpiry.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex max-w-sm flex-col gap-3" noValidate>
      <FormField
        id="expiry_hours"
        label="Drafts stay valid for (hours)"
        error={errors.expiry_hours}
      >
        <Input
          id="expiry_hours"
          name="expiry_hours"
          type="number"
          min={1}
          max={720}
          defaultValue={settings.expiry_hours}
          required
        />
      </FormField>
      <FormField
        id="remind_after_hours"
        label="Remind approvers after (hours)"
        hint="A task appears for admins and owners when a reply still waits for approval."
        error={errors.remind_after_hours}
      >
        <Input
          id="remind_after_hours"
          name="remind_after_hours"
          type="number"
          min={1}
          max={168}
          defaultValue={settings.remind_after_hours}
          required
        />
      </FormField>
      <FormField
        id="escalate_after_hours"
        label="Mark it urgent after (hours)"
        error={errors.escalate_after_hours}
      >
        <Input
          id="escalate_after_hours"
          name="escalate_after_hours"
          type="number"
          min={2}
          max={720}
          defaultValue={settings.escalate_after_hours}
          required
        />
      </FormField>
      <Button type="submit" variant="outline" disabled={pending}>
        Save
      </Button>
      <FormStatus state={state} />
    </form>
  );
}
