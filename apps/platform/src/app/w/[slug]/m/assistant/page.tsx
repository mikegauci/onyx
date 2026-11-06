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

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Sales assistant</h1>
        <p className="text-sm">
          Open a conversation in the{" "}
          <Link className="underline" href={inboxPath(slug, "conversations")}>
            inbox
          </Link>{" "}
          and choose <strong>Draft with assistant</strong>. The assistant reads the thread, looks up
          products, stock and the policies below, and proposes a reply.
        </p>
        <ul className="text-muted-foreground list-disc pl-5 text-sm">
          <li>The draft reply is added as an internal note. Nothing is sent to the customer.</li>
          <li>
            When every product, price, VAT rate and stock level checks out, Onyx creates a draft
            quote with prices and totals calculated from the catalogue. Staff approve it.
          </li>
          <li>Otherwise the conversation goes to staff with the reasons listed.</li>
        </ul>
      </div>

      <section className="flex flex-col gap-4" aria-labelledby="policies-heading">
        <div className="flex flex-col gap-1">
          <h2 id="policies-heading" className="text-lg font-medium">
            Policies
          </h2>
          <p className="text-muted-foreground text-sm">
            The only shop policies the assistant may quote. Without a policy on a topic, it says a
            colleague will confirm.
          </p>
        </div>
        {policies.length === 0 ? (
          <p className="text-muted-foreground text-sm">No policies yet.</p>
        ) : (
          <ul className="flex flex-col gap-4" aria-label="Policies">
            {policies.map((policy) => (
              <li key={policy.topic} className="flex flex-col gap-2 rounded-md border p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-medium">{policy.title}</h3>
                  <span className="text-muted-foreground font-mono text-xs">
                    {topicLabel(policy.topic)} · {policy.topic}
                  </span>
                </div>
                <p className="text-sm whitespace-pre-wrap">{policy.body}</p>
                {canManage ? (
                  <details className="flex flex-col gap-3">
                    <summary className="cursor-pointer text-sm underline">
                      Edit {policy.title}
                    </summary>
                    <div className="mt-3 flex flex-col gap-3">
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
          <section className="flex flex-col gap-3" aria-labelledby="new-policy-heading">
            <h3 id="new-policy-heading" className="font-medium">
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
