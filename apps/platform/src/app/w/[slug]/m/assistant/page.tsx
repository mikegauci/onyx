import { Badge } from "@onyx/ui/components/badge";
import { PageHeader } from "@onyx/ui/components/page";
import { FileCheck2, MessageSquareText, UserRound } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { assistantPath, topicLabel } from "@/lib/assistant";
import { requireOk } from "@/lib/guards";
import { inboxPath } from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { DeletePolicyForm, PolicyForm } from "./_components/policy-forms";

export default async function AssistantPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = assistantPath(slug);
  // The API decides: a disabled module is 403, shown as the not-found page.
  requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: "assistant" } } }),
    ),
    path,
  );
  const workspace = await workspaceWith(slug, "assistant.run", path);
  const policies = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/assistant/policies", { params: { path: { slug } } }),
    ),
    path,
  );
  const canManage = workspace.permissions.includes("assistant.manage");

  const steps = [
    {
      icon: MessageSquareText,
      title: "Drafts a reply",
      body: "The draft is added to the conversation as an internal note. Nothing is sent to the customer.",
    },
    {
      icon: FileCheck2,
      title: "Prepares a quote",
      body: "When every product, price, VAT rate and stock level checks out, Onyx creates a draft quote from the catalogue. Staff approve it.",
    },
    {
      icon: UserRound,
      title: "Or hands over",
      body: "Otherwise the conversation goes to staff, with the reasons listed.",
    },
  ];

  return (
    <div className="flex max-w-4xl flex-col gap-8">
      <PageHeader
        eyebrow="Module"
        title="Sales assistant"
        description={
          <>
            Open a conversation in the{" "}
            <Link
              className="text-brand underline-offset-4 hover:underline"
              href={inboxPath(slug, "conversations")}
            >
              inbox
            </Link>{" "}
            and choose <strong className="text-foreground">Draft with assistant</strong>. The
            assistant reads the thread, looks up products, stock and the policies below, and
            proposes a reply.
          </>
        }
      />

      <ol className="bg-border grid gap-px overflow-hidden rounded-2xl border sm:grid-cols-3">
        {steps.map((step, i) => (
          <li key={step.title} className="bg-card flex flex-col gap-3 p-5">
            <span className="flex items-center gap-3">
              <span className="bg-brand/10 text-brand flex size-9 items-center justify-center rounded-xl">
                <step.icon aria-hidden className="size-4" />
              </span>
              <span className="text-muted-foreground font-mono text-[11px] tracking-[0.2em]">
                0{i + 1}
              </span>
            </span>
            <span className="font-medium">{step.title}</span>
            <span className="text-muted-foreground text-sm">{step.body}</span>
          </li>
        ))}
      </ol>

      <section className="flex flex-col gap-4" aria-labelledby="policies-heading">
        <div className="flex flex-col gap-1">
          <h2 id="policies-heading" className="text-lg font-light tracking-tight">
            Policies
          </h2>
          <p className="text-muted-foreground text-sm">
            The only shop policies the assistant may quote. Without a policy on a topic, it says a
            colleague will confirm.
          </p>
        </div>
        {policies.length === 0 ? (
          <p className="text-muted-foreground rounded-2xl border border-dashed px-5 py-4 text-sm">
            No policies yet.
          </p>
        ) : (
          <ul className="bg-card divide-y rounded-2xl border" aria-label="Policies">
            {policies.map((policy) => (
              <li key={policy.topic} className="flex flex-col gap-2 px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium">{policy.title}</h3>
                  <Badge variant="secondary" className="font-mono">
                    {topicLabel(policy.topic)} · {policy.topic}
                  </Badge>
                </div>
                <p className="text-muted-foreground text-sm whitespace-pre-wrap">{policy.body}</p>
                {canManage ? (
                  <details className="group flex flex-col gap-3">
                    <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-sm">
                      Edit {policy.title}
                    </summary>
                    <div className="bg-background/40 mt-3 flex flex-col gap-3 rounded-xl border p-4">
                      <PolicyForm slug={slug} policy={policy} />
                      <DeletePolicyForm slug={slug} policy={policy} />
                    </div>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canManage ? (
          <section
            className="bg-card flex flex-col gap-4 rounded-2xl border p-5"
            aria-labelledby="new-policy-heading"
          >
            <h3 id="new-policy-heading" className="text-sm font-medium">
              Add a policy
            </h3>
            <PolicyForm slug={slug} />
          </section>
        ) : (
          <p className="text-muted-foreground text-xs">Admins and owners can edit policies.</p>
        )}
      </section>
    </div>
  );
}
