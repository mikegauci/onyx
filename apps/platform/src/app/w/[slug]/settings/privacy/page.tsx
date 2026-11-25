import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { RetentionForm } from "./retention-form";

type Props = { params: Promise<{ slug: string }> };

export default async function PrivacySettingsPage({ params }: Props) {
  const { slug } = await params;
  const path = `/w/${slug}/settings/privacy`;
  await workspaceWith(slug, "privacy.manage", path);
  const settings = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/privacy/settings", { params: { path: { slug } } }),
    ),
    path,
  );
  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="retention-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <div className="flex flex-col gap-1">
          <h2 id="retention-heading" className="text-base font-medium tracking-tight">
            Conversation retention
          </h2>
          <p className="text-muted-foreground text-sm">
            Remove the text of conversations nobody has touched for a while: messages, names and
            addresses. The conversation stays as an empty record, so counts in Insights stay right.
            Contacts, quotes and deals are not affected. This runs every 30 minutes and cannot be
            undone.
          </p>
        </div>
        <RetentionForm
          slug={slug}
          months={settings.conversation_retention_months ?? null}
          choices={settings.choices}
        />
      </section>
      <section
        aria-labelledby="requests-heading"
        className="bg-card flex flex-col gap-2 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="requests-heading" className="text-base font-medium tracking-tight">
          Requests from a person
        </h2>
        <p className="text-muted-foreground text-sm">
          To give someone a copy of their data, or to erase them, open their contact in CRM and use
          the Privacy panel there.
        </p>
      </section>
    </div>
  );
}
