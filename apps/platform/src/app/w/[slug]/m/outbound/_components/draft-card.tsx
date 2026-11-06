"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import Link from "next/link";
import { useActionState, useState } from "react";

import { formatInZone } from "@/lib/crm";
import { IDLE } from "@/lib/form-state";
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
  approveDraft,
  createDraft,
  rejectDraft,
  reviseDraft,
  sendDraft,
  updateExpiry,
} from "../actions";

const TEXTAREA_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-32 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none aria-invalid:border-destructive";

type QuoteOption = { id: string; label: string };

/** Write a reply for approval, optionally with one of the contact's quotes. */
export function NewDraftForm({
  slug,
  conversationId,
  quotes,
}: {
  slug: string;
  conversationId: string;
  quotes: QuoteOption[];
}) {
  const [state, action, pending] = useActionState(
    createDraft.bind(null, slug, conversationId),
    IDLE,
  );
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex flex-col gap-3" noValidate>
      <FormField id="draft-body" label="Reply to the customer" error={errors.body}>
        <textarea
          id="draft-body"
          name="body"
          required
          maxLength={10000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      {quotes.length > 0 ? (
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
      <Button type="submit" disabled={pending}>
        {pending ? "Saving…" : "Save for approval"}
      </Button>
      <FormStatus state={state} />
    </form>
  );
}

function QuoteLine({ slug, draft }: { slug: string; draft: DraftDetail }) {
  if (!draft.quote) return null;
  const quote = draft.quote;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>
        With quote{" "}
        <Link className="underline" href={quotationsPath(slug, "quotes", quote.id)}>
          {quote.number}
        </Link>{" "}
        (version {quote.approved_version ?? quote.version}, {quote.status})
      </p>
      {quote.blocked ? (
        <p className="text-warning-foreground bg-warning/20 rounded px-2 py-1 text-xs">
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
  const busy = revising || approving || rejecting || sending;
  const editable = controls.canEdit || controls.canApprove;

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
          className="text-sm underline"
          href={`/w/${encodeURIComponent(slug)}/m/inbox/conversations/${draft.conversation_id}`}
        >
          Conversation: {draft.conversation_subject}
        </Link>
      ) : null}
      {draft.expiry ? (
        <p role="note" className="rounded-md border p-2 text-sm">
          {draft.expiry.message}
        </p>
      ) : null}
      {draft.status === "rejected" && draft.rejection_reason ? (
        <p className="text-sm">
          Rejected by {draft.decided_by?.label ?? "a reviewer"}: {draft.rejection_reason}
        </p>
      ) : null}
      <QuoteLine slug={slug} draft={draft} />

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
        <blockquote className="rounded-md border p-3 text-sm whitespace-pre-wrap">
          {draft.body}
        </blockquote>
      )}

      <div className="flex flex-wrap gap-2">
        {controls.canEdit ? (
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

      <FormStatus state={reviseState} />
      <FormStatus state={approveState} />
      <FormStatus state={sendState} />

      {controls.canReject ? (
        <details>
          <summary className="cursor-pointer text-sm underline">Reject this reply</summary>
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
          <summary className="cursor-pointer text-sm underline">
            All revisions ({draft.revisions.length})
          </summary>
          <ol className="mt-2 flex flex-col gap-2" aria-label="Revisions">
            {draft.revisions.map((revision) => (
              <li key={revision.revision} className="border-l-2 pl-3 text-sm">
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
        <Link className="text-xs underline" href={outboundPath(slug, "drafts", draft.id)}>
          Open the draft page
        </Link>
      ) : null}
    </article>
  );
}

export function ExpiryForm({ slug, hours }: { slug: string; hours: number }) {
  const [state, action, pending] = useActionState(updateExpiry.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex max-w-sm flex-col gap-2" noValidate>
      <FormField
        id="expiry_hours"
        label="Drafts stay valid for (hours)"
        error={state.fieldErrors?.expiry_hours}
      >
        <Input
          id="expiry_hours"
          name="expiry_hours"
          type="number"
          min={1}
          max={720}
          defaultValue={hours}
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
