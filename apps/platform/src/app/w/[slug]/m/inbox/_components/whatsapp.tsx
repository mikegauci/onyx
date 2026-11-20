"use client";

import { Button } from "@onyx/ui/components/button";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import { syncWhatsAppTemplates } from "../actions";

/** Fetch the business account's templates from Meta. Managers only; the API checks it. */
export function SyncTemplatesButton({
  slug,
  channelId,
  channelName,
}: {
  slug: string;
  channelId: string;
  channelName: string;
}) {
  const [state, action, pending] = useActionState(
    syncWhatsAppTemplates.bind(null, slug, channelId),
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
        aria-label={`Refresh templates for ${channelName} from WhatsApp`}
      >
        {pending ? "Refreshing…" : "Refresh from WhatsApp"}
      </Button>
    </form>
  );
}
