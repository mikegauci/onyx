"use client";

import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import Link from "next/link";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";
import { knowledgePath, MATCH_LABEL, pageLabel } from "@/lib/knowledge";

import { FormStatus } from "../../../settings/form-status";
import { searchKnowledge, type SearchState } from "../actions";

/** Search the workspace's documents the way the assistant does, with page citations. */
export function KnowledgeSearch({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(
    searchKnowledge.bind(null, slug),
    IDLE as SearchState,
  );
  const result = state.result;
  return (
    <div className="flex flex-col gap-4">
      <form action={action} role="search" className="flex max-w-xl flex-col gap-3">
        <FormField
          id="knowledge-query"
          label="Question"
          hint="Ask in a sentence, the way a customer would."
          error={state.fieldErrors?.query}
        >
          <Input
            id="knowledge-query"
            name="query"
            required
            minLength={2}
            maxLength={500}
            defaultValue={state.query}
          />
        </FormField>
        <Button type="submit" disabled={pending} className="self-start">
          {pending ? "Searching…" : "Search"}
        </Button>
      </form>
      <FormStatus state={state} />
      {result ? (
        <section
          aria-labelledby="results-heading"
          aria-live="polite"
          className="flex flex-col gap-3"
        >
          <h3 id="results-heading" className="text-base font-medium">
            Results
          </h3>
          {result.mode === "keyword" ? (
            <p className="text-muted-foreground text-sm">
              AI search is unavailable right now, so these results match keywords only.
            </p>
          ) : null}
          {result.abstained ? (
            <p className="text-sm">
              No passage answers this well enough. The assistant would say a colleague will confirm
              rather than guess.
            </p>
          ) : (
            <ol className="flex flex-col gap-3" aria-label="Matching passages">
              {result.hits.map((hit) => (
                <li key={hit.chunk_id} className="rounded-md border p-3">
                  <p className="text-sm font-medium">
                    <Link
                      className="underline-offset-4 hover:underline"
                      href={knowledgePath(slug, "documents", hit.document_id)}
                    >
                      {hit.document_title}
                    </Link>
                    {pageLabel(hit.page) ? (
                      <span className="text-muted-foreground"> · {pageLabel(hit.page)}</span>
                    ) : null}
                  </p>
                  <p className="mt-2 text-sm whitespace-pre-line">{hit.content}</p>
                  <p className="mt-2 flex gap-1">
                    {hit.matched_by.map((m) => (
                      <Badge key={m} variant="outline">
                        {MATCH_LABEL[m]}
                      </Badge>
                    ))}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>
      ) : null}
    </div>
  );
}
