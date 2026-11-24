"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useActionState } from "react";

import {
  type AssistantRun,
  OUTCOME_LABEL,
  OUTCOME_VARIANT,
  runBlockedReason,
  usdFromMicros,
} from "@/lib/assistant";
import { formatInZone } from "@/lib/crm";
import type { ConversationStatus } from "@/lib/inbox";
import { knowledgePath, pageLabel } from "@/lib/knowledge";
import { quotationsPath } from "@/lib/quotations";

import { FormStatus } from "../../../settings/form-status";
import { type RunState, runAssistant } from "../../assistant/actions";

const IDLE: RunState = { status: "idle" };

/** The outcome of one run: a quote link when drafted, the API's reasons when handed to staff. */
export function RunSummary({ slug, run }: { slug: string; run: AssistantRun }) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      <Badge variant={OUTCOME_VARIANT[run.outcome]} className="self-start">
        {OUTCOME_LABEL[run.outcome]}
      </Badge>
      {run.quote ? (
        <Link
          className="text-brand underline-offset-4 hover:underline"
          href={quotationsPath(slug, "quotes", run.quote.id)}
        >
          Draft quote {run.quote.number}
        </Link>
      ) : null}
      {run.reasons.length > 0 ? (
        <ul
          className="text-muted-foreground marker:text-foreground/30 list-disc pl-5"
          aria-label="Reasons"
        >
          {run.reasons.map((reason) => (
            <li key={reason.code}>{reason.message}</li>
          ))}
        </ul>
      ) : null}
      {run.sources.length > 0 ? (
        <div>
          <p className="text-muted-foreground text-xs">Sources</p>
          <ul className="list-disc pl-5" aria-label="Sources">
            {run.sources.map((source) => (
              <li key={source.chunk_id}>
                {source.document_id && source.document_title ? (
                  <Link
                    className="text-brand underline-offset-4 hover:underline"
                    href={knowledgePath(slug, "documents", source.document_id)}
                  >
                    {source.document_title}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">A removed document</span>
                )}
                {pageLabel(source.page) ? `, ${pageLabel(source.page)?.toLowerCase()}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function AssistantPanel({
  slug,
  conversationId,
  status,
  runs,
  timezone,
}: {
  slug: string;
  conversationId: string;
  status: ConversationStatus;
  runs: AssistantRun[];
  timezone: string;
}) {
  const [state, action, pending] = useActionState(
    runAssistant.bind(null, slug, conversationId),
    IDLE,
  );
  const blocked = runBlockedReason(status);
  return (
    <section
      className="bg-card flex flex-col gap-4 rounded-2xl border p-5"
      aria-labelledby="assistant-heading"
    >
      <div className="flex flex-col gap-1">
        <h3 id="assistant-heading" className="flex items-center gap-2 text-sm font-medium">
          <Sparkles aria-hidden className="text-brand size-4" />
          Sales assistant
        </h3>
        <p className="text-muted-foreground text-xs">
          Drafts a reply as an internal note and, when every product checks out, a draft quote.
          Nothing is sent to the customer.
        </p>
      </div>
      <form action={action} className="flex flex-col gap-2">
        <Button
          type="submit"
          variant="secondary"
          disabled={pending || blocked !== null}
          aria-describedby="assistant-hint"
        >
          <Sparkles aria-hidden className={pending ? "animate-pulse" : undefined} />
          {pending ? "Drafting…" : "Draft with assistant"}
        </Button>
        <p id="assistant-hint" className="text-muted-foreground text-xs" aria-live="polite">
          {pending ? "Drafting… this can take up to 30 seconds." : (blocked ?? "")}
        </p>
      </form>
      {/* The new run also heads the list below once the page refreshes. */}
      <FormStatus state={state} />
      {runs.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h4 className="text-muted-foreground border-t pt-4 font-mono text-[11px] tracking-[0.15em] uppercase">
            Recent runs
          </h4>
          <ol className="flex flex-col gap-3" aria-label="Recent assistant runs">
            {runs.map((run) => (
              <li key={run.id} className="flex flex-col gap-1.5">
                <RunSummary slug={slug} run={run} />
                <p className="text-muted-foreground text-xs">
                  <time dateTime={run.created_at}>{formatInZone(run.created_at, timezone)}</time>
                  {run.cost_usd_micros > 0 ? ` · ${usdFromMicros(run.cost_usd_micros)}` : ""}
                </p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
