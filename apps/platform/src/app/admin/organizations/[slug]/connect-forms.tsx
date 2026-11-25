"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus, SELECT_CLASS } from "../../../w/[slug]/settings/form-status";
import { connectPhoneLine, connectWhatsApp } from "../actions";

/** Platform admins only: the number routes Meta's webhooks to this organisation. */
export function ConnectWhatsAppForm({ slug, configured }: { slug: string; configured: boolean }) {
  const [state, action, pending] = useActionState(connectWhatsApp.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  return (
    <form
      action={action}
      className="flex flex-col gap-4"
      noValidate
      aria-label="Connect a WhatsApp number"
    >
      <FormStatus state={state} />
      {!configured ? (
        <p className="text-warning text-sm">
          WhatsApp is not set up on this server yet, so a connected number will not send or receive
          until it is.
        </p>
      ) : null}
      <p className="text-muted-foreground text-sm">
        Check the number belongs to this client in Meta Business Manager first. The ids are in
        WhatsApp Manager → Phone numbers (or the app’s API Setup page).
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="wa-display"
          label="Phone number"
          hint="As customers see it, e.g. +356 2100 0000."
          error={errors.display_phone_number}
        >
          <Input id="wa-display" name="display_phone_number" required maxLength={32} />
        </FormField>
        <FormField
          id="wa-channel"
          label="Channel name"
          hint="Shown in the client's inbox. An existing WhatsApp channel with this name gets the number."
          error={errors.channel_name}
        >
          <Input id="wa-channel" name="channel_name" defaultValue="WhatsApp" maxLength={100} />
        </FormField>
        <FormField
          id="wa-number-id"
          label="Phone number ID"
          hint="Digits only."
          error={errors.phone_number_id}
        >
          <Input id="wa-number-id" name="phone_number_id" inputMode="numeric" required />
        </FormField>
        <FormField
          id="wa-waba"
          label="WhatsApp Business account ID"
          hint="Digits only. Used to load the message templates."
          error={errors.waba_id}
        >
          <Input id="wa-waba" name="waba_id" inputMode="numeric" required />
        </FormField>
      </div>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Connecting…" : "Connect WhatsApp number"}
      </Button>
    </form>
  );
}

export function ConnectPhoneLineForm({
  slug,
  configured,
  whatsappChannels,
}: {
  slug: string;
  configured: boolean;
  whatsappChannels: string[];
}) {
  const [state, action, pending] = useActionState(connectPhoneLine.bind(null, slug), IDLE);
  const errors = state.fieldErrors ?? {};
  if (whatsappChannels.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Connect a WhatsApp number first: missed calls are threaded into its conversations and the
        text-back is sent from it.
      </p>
    );
  }
  return (
    <form
      action={action}
      className="flex flex-col gap-4"
      noValidate
      aria-label="Connect a phone line"
    >
      <FormStatus state={state} />
      {!configured ? (
        <p className="text-warning text-sm">
          The telephony provider is not set up on this server yet, so calls to this number will not
          reach Onyx until it is.
        </p>
      ) : null}
      <p className="text-muted-foreground text-sm">
        The cloud number bought for this client. Their carrier forwards unanswered calls to it.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="line-number"
          label="Cloud number"
          hint="International format, e.g. +35627000000."
          error={errors.number}
        >
          <Input id="line-number" name="number" required inputMode="tel" maxLength={20} />
        </FormField>
        <FormField
          id="line-channel"
          label="WhatsApp channel"
          hint="Text-backs are sent from this number."
          error={errors.whatsapp_channel_name}
        >
          <select id="line-channel" name="whatsapp_channel_name" className={SELECT_CLASS}>
            {whatsappChannels.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </FormField>
      </div>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Connecting…" : "Connect phone line"}
      </Button>
    </form>
  );
}
