"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useEffect, useRef, useState } from "react";

import { IDLE } from "@/lib/form-state";
import {
  type Assignee,
  type Channel,
  CHANNEL_KIND_LABEL,
  type ComposeKind,
  composeKinds,
  type ConversationDetail,
  STATUS_ACTION,
} from "@/lib/inbox";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import {
  assignConversation,
  changeStatus,
  createChannel,
  createConversation,
  handoff,
  linkContact,
  postMessage,
  setChannelDisabled,
  updateEmailSettings,
} from "../actions";

const TEXTAREA_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-24 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none aria-invalid:border-destructive";

type Option = { id: string; label: string };

/** One key per message: a resubmitted request is recorded once by the API. */
function newKey(): string {
  return crypto.randomUUID();
}

export function NewConversationForm({
  slug,
  channels,
  contacts,
}: {
  slug: string;
  channels: Channel[];
  contacts: Option[];
}) {
  const [state, action, pending] = useActionState(createConversation.bind(null, slug), IDLE);
  // Success redirects away, so one key per visit is enough.
  const [key] = useState(newKey);
  const errors = state.fieldErrors ?? {};
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4" noValidate>
      <FormStatus state={state} />
      <input type="hidden" name="idempotency_key" value={key} />
      <FormField id="channel_id" label="Channel" error={errors.channel_id}>
        <select
          id="channel_id"
          name="channel_id"
          className={SELECT_CLASS}
          required
          defaultValue={(channels.find((c) => c.kind === "manual") ?? channels[0])?.id}
        >
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </FormField>
      <FormField id="subject" label="Subject" error={errors.subject}>
        <Input id="subject" name="subject" required maxLength={200} />
      </FormField>
      <FormField id="body" label="What the customer said" error={errors.body}>
        <textarea id="body" name="body" required maxLength={10000} className={TEXTAREA_CLASS} />
      </FormField>
      <FormField id="contact_id" label="Existing contact" error={errors.contact_id}>
        <select id="contact_id" name="contact_id" className={SELECT_CLASS} defaultValue="">
          <option value="">Not a saved contact</option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </FormField>
      <fieldset className="flex flex-col gap-3 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">Or the customer&apos;s details</legend>
        {errors.sender ? (
          <p className="text-destructive text-sm" role="alert">
            {errors.sender}
          </p>
        ) : null}
        <FormField id="sender_name" label="Name" error={errors.name}>
          <Input id="sender_name" name="sender_name" maxLength={200} />
        </FormField>
        <FormField id="sender_email" label="Email" error={errors.email}>
          <Input id="sender_email" name="sender_email" type="email" maxLength={320} />
        </FormField>
        <FormField id="sender_phone" label="Phone" error={errors.phone}>
          <Input id="sender_phone" name="sender_phone" type="tel" maxLength={32} />
        </FormField>
        <p className="text-muted-foreground text-xs">
          A matching email or phone links the conversation to the CRM contact automatically.
        </p>
      </fieldset>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Record conversation"}
      </Button>
    </form>
  );
}

const KIND_LABEL: Record<ComposeKind, string> = {
  reply: "Log a reply",
  customer: "Log a customer message",
  note: "Add an internal note",
};

export function ComposeForm({
  slug,
  conversation,
}: {
  slug: string;
  conversation: ConversationDetail;
}) {
  const [state, action, pending] = useActionState(
    postMessage.bind(null, slug, conversation.id),
    IDLE,
  );
  const kinds = composeKinds(conversation.channel.kind);
  const email = conversation.channel.kind === "email";
  const [kind, setKind] = useState<ComposeKind>(
    conversation.status === "closed" || !kinds.includes("reply") ? "note" : "reply",
  );
  const [initialKey] = useState(newKey);
  const form = useRef<HTMLFormElement>(null);
  const keyInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (state.status !== "ok") return;
    form.current?.reset();
    // The next message is a new request with a new key.
    if (keyInput.current) keyInput.current.value = newKey();
  }, [state]);
  const closed = conversation.status === "closed";
  return (
    <form ref={form} action={action} className="flex flex-col gap-3" noValidate>
      <FormStatus state={state} />
      <input ref={keyInput} type="hidden" name="idempotency_key" defaultValue={initialKey} />
      <fieldset className="flex flex-wrap gap-4">
        <legend className="sr-only">Message type</legend>
        {kinds.map((k) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="kind"
              value={k}
              checked={kind === k}
              disabled={k === "reply" && closed}
              onChange={() => setKind(k)}
            />
            {KIND_LABEL[k]}
          </label>
        ))}
      </fieldset>
      <FormField id="message-body" label="Message" error={state.fieldErrors?.body}>
        <textarea
          id="message-body"
          name="body"
          required
          maxLength={10000}
          className={TEXTAREA_CLASS}
        />
      </FormField>
      {email ? (
        <p className="text-muted-foreground text-xs">
          To answer the customer by email, use Reply for approval. The approved text is emailed from
          Onyx.
        </p>
      ) : null}
      {kind === "reply" ? (
        <p className="text-muted-foreground text-xs">
          Onyx records the reply; it does not send it. Use this after replying by phone or in
          person.
        </p>
      ) : null}
      <div className="flex flex-wrap items-end gap-3">
        {kind !== "note" ? (
          <FormField id="set_status" label="Then" className="sm:w-64">
            <select id="set_status" name="set_status" className={SELECT_CLASS} defaultValue="">
              <option value="">Keep the status</option>
              {kind === "reply" ? (
                <option value="waiting_on_customer">Mark waiting on customer</option>
              ) : null}
              <option value="closed">Close</option>
            </select>
          </FormField>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : KIND_LABEL[kind]}
        </Button>
      </div>
      {closed && !email ? (
        <p className="text-muted-foreground text-xs">Reopen the conversation to log a reply.</p>
      ) : null}
    </form>
  );
}

export function AssignForm({
  slug,
  conversation,
  assignees,
  me,
}: {
  slug: string;
  conversation: ConversationDetail;
  assignees: Assignee[];
  me: string;
}) {
  const [state, action, pending] = useActionState(
    assignConversation.bind(null, slug, conversation.id),
    IDLE,
  );
  const current = conversation.assignee?.user_id ?? "";
  return (
    <div className="flex flex-col gap-2">
      <FormStatus state={state} />
      <form action={action} className="flex flex-wrap items-end gap-2">
        <FormField id="assignee" label="Assigned to" className="sm:w-64">
          <select
            id="assignee"
            name="assignee_user_id"
            className={SELECT_CLASS}
            defaultValue={current}
            key={current}
          >
            <option value="">Unassigned</option>
            {assignees.map((a) => (
              <option key={a.user_id} value={a.user_id}>
                {a.display_name}
              </option>
            ))}
          </select>
        </FormField>
        <Button type="submit" variant="outline" disabled={pending}>
          Assign
        </Button>
      </form>
      {current !== me ? (
        <form action={action}>
          <input type="hidden" name="assignee_user_id" value={me} />
          <Button type="submit" variant="link" size="sm" className="px-0" disabled={pending}>
            Assign to me
          </Button>
        </form>
      ) : null}
    </div>
  );
}

export function StatusForm({
  slug,
  conversation,
}: {
  slug: string;
  conversation: ConversationDetail;
}) {
  const [state, action, pending] = useActionState(
    changeStatus.bind(null, slug, conversation.id),
    IDLE,
  );
  return (
    <div className="flex flex-col gap-2">
      <FormStatus state={state} />
      <form action={action} className="flex flex-wrap gap-2">
        {conversation.allowed_statuses.map((status) => (
          <Button
            key={status}
            type="submit"
            name="status"
            value={status}
            variant={status === "closed" ? "outline" : "default"}
            disabled={pending}
          >
            {STATUS_ACTION[status]}
          </Button>
        ))}
      </form>
    </div>
  );
}

export function HandoffForm({
  slug,
  conversation,
  canManage,
}: {
  slug: string;
  conversation: ConversationDetail;
  canManage: boolean;
}) {
  const [state, action, pending] = useActionState(handoff.bind(null, slug, conversation.id), IDLE);
  if (conversation.handler === "staff") {
    return (
      <div className="flex flex-col gap-2">
        <FormStatus state={state} />
        <p className="text-sm">
          Handled by staff
          {conversation.handoff_reason ? ` · ${conversation.handoff_reason}` : ""}
        </p>
        {canManage ? (
          <form action={action}>
            <input type="hidden" name="handler" value="assistant" />
            <Button type="submit" variant="outline" size="sm" disabled={pending}>
              Hand to the assistant
            </Button>
          </form>
        ) : null}
      </div>
    );
  }
  return (
    <form action={action} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <p className="text-sm">Handled by the assistant (drafts only; staff approve every reply).</p>
      <input type="hidden" name="handler" value="staff" />
      <FormField
        id="reason"
        label="Why a person should take over"
        error={state.fieldErrors?.reason}
      >
        <Input id="reason" name="reason" required maxLength={500} />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        Hand to staff
      </Button>
    </form>
  );
}

export function LinkContactForm({
  slug,
  conversation,
  contacts,
}: {
  slug: string;
  conversation: ConversationDetail;
  contacts: Option[];
}) {
  const [state, action, pending] = useActionState(
    linkContact.bind(null, slug, conversation.id),
    IDLE,
  );
  const current = conversation.contact?.id ?? "";
  return (
    <form action={action} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <div className="flex flex-wrap items-end gap-2">
        <FormField
          id="link-contact"
          label="CRM contact"
          error={state.fieldErrors?.contact_id ?? state.fieldErrors?.lead_id}
          className="sm:w-64"
        >
          <select
            id="link-contact"
            name="contact_id"
            className={SELECT_CLASS}
            defaultValue={current}
            key={current}
          >
            <option value="">No contact</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </FormField>
        <Button type="submit" variant="outline" disabled={pending}>
          Save contact
        </Button>
      </div>
    </form>
  );
}

export function ChannelForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(createChannel.bind(null, slug), IDLE);
  const [kind, setKind] = useState<Channel["kind"]>("manual");
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status !== "ok") return;
    form.current?.reset();
    setKind("manual");
  }, [state]);
  return (
    <form ref={form} action={action} className="flex max-w-md flex-col gap-3">
      <FormStatus state={state} />
      <FormField id="channel-name" label="Channel name" error={state.fieldErrors?.name}>
        <Input id="channel-name" name="name" required maxLength={100} placeholder="Shop phone" />
      </FormField>
      <FormField id="channel-kind" label="Kind" error={state.fieldErrors?.kind}>
        <select
          id="channel-kind"
          name="kind"
          className={SELECT_CLASS}
          value={kind}
          onChange={(e) => setKind(e.target.value as Channel["kind"])}
        >
          {(Object.keys(CHANNEL_KIND_LABEL) as Channel["kind"][]).map((k) => (
            <option key={k} value={k}>
              {CHANNEL_KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </FormField>
      {kind === "email" ? (
        <EmailSenderFields errors={state.fieldErrors} />
      ) : (
        <p className="text-muted-foreground text-xs">
          Phone / in-person and email channels work today. WhatsApp and website channels can be
          added now and will connect in a later release.
        </p>
      )}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Add channel"}
      </Button>
    </form>
  );
}

export function ChannelToggle({ slug, channel }: { slug: string; channel: Channel }) {
  const disabled = channel.disabled_at !== null;
  const [state, action, pending] = useActionState(
    setChannelDisabled.bind(null, slug, channel.id, !disabled),
    IDLE,
  );
  return (
    <form action={action} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <Button
        type="submit"
        variant="outline"
        size="sm"
        disabled={pending}
        className="self-start"
        aria-label={`${disabled ? "Enable" : "Disable"} channel ${channel.name}`}
      >
        {disabled ? "Enable" : "Disable"}
      </Button>
    </form>
  );
}

function EmailSenderFields({
  errors,
  channel,
}: {
  errors?: Record<string, string | undefined>;
  channel?: Channel;
}) {
  const id = channel ? `-${channel.id}` : "";
  return (
    <>
      <FormField
        id={`from_name${id}`}
        label="Sender name"
        hint="Customers see this as who the email is from. Empty uses the workspace name."
        error={errors?.from_name}
      >
        <Input
          id={`from_name${id}`}
          name="from_name"
          maxLength={100}
          defaultValue={channel?.from_name ?? ""}
        />
      </FormField>
      <FormField
        id={`signature${id}`}
        label="Signature"
        hint="Added below every emailed reply."
        error={errors?.signature}
      >
        <textarea
          id={`signature${id}`}
          name="signature"
          maxLength={1000}
          defaultValue={channel?.signature ?? ""}
          className={TEXTAREA_CLASS}
        />
      </FormField>
    </>
  );
}

/** The sender name and signature of an email channel. */
export function EmailSettingsForm({ slug, channel }: { slug: string; channel: Channel }) {
  const [state, action, pending] = useActionState(
    updateEmailSettings.bind(null, slug, channel.id),
    IDLE,
  );
  return (
    <form action={action} className="flex max-w-md flex-col gap-3" noValidate>
      <FormStatus state={state} />
      <EmailSenderFields errors={state.fieldErrors} channel={channel} />
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save sender details"}
      </Button>
    </form>
  );
}

/** Copy the channel's inbound address; the address stays visible and selectable without it. */
export function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <code className="bg-muted rounded px-2 py-1 text-xs break-all">{address}</code>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          void navigator.clipboard?.writeText(address).then(() => setCopied(true));
        }}
        aria-label={`Copy address ${address}`}
      >
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}
