"use client";

import { Button } from "@onyx/ui/components/button";
import { useActionState } from "react";

import { CopyLink } from "@/components/brand-fields";
import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { type LinkState, requestDocuments, revokeUploadLink } from "../actions";

type ActiveLink = { expires_at: string; upload_count: number; max_uploads: number };

export function RequestDocuments({
  slug,
  dealId,
  conversationId,
  canPrepareReply,
  firstName,
  active,
  expiresLabel,
}: {
  slug: string;
  dealId: string;
  conversationId: string | null;
  canPrepareReply: boolean;
  firstName: string;
  active: ActiveLink | null;
  expiresLabel: string | null;
}) {
  const [state, action, pending] = useActionState<LinkState, FormData>(
    requestDocuments.bind(null, slug, dealId, conversationId),
    IDLE,
  );
  const [revoked, revoke, revoking] = useActionState(
    revokeUploadLink.bind(null, slug, dealId),
    IDLE,
  );
  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">
        The customer gets a private page, valid for 7 days, showing only the documents still needed.
        They can take photos with their phone. Nothing is sent without approval.
      </p>
      {active && !state.link ? (
        <div className="flex flex-col gap-2 text-sm">
          <p>
            A link is active until {expiresLabel}. {active.upload_count} upload
            {active.upload_count === 1 ? "" : "s"} so far.
          </p>
          <form action={revoke}>
            <FormStatus state={revoked} />
            <Button type="submit" variant="outline" size="sm" disabled={revoking}>
              {revoking ? "Stopping…" : "Stop this link"}
            </Button>
          </form>
        </div>
      ) : null}
      <form action={action} className="flex flex-col gap-3" aria-label="Request documents">
        <FormStatus state={state} />
        {state.link ? <CopyLink link={state.link} label="Upload link (shown once)" /> : null}
        <input type="hidden" name="first_name" value={firstName} />
        {canPrepareReply ? (
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              name="prepare"
              defaultChecked
              className="accent-brand mt-0.5 size-4"
            />
            <span>
              Prepare a reply with the link in the customer&apos;s conversation (it waits for
              approval). Outside WhatsApp&apos;s 24-hour window, send it with an approved template
              instead.
            </span>
          </label>
        ) : null}
        <Button type="submit" variant="secondary" disabled={pending} className="self-start">
          {pending ? "Creating…" : active ? "Make a new link" : "Request documents"}
        </Button>
      </form>
    </div>
  );
}
