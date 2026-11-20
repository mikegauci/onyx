import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { IntegrationList } from "./integration-list";

type Props = { params: Promise<{ slug: string }> };

export default async function IntegrationsSettingsPage({ params }: Props) {
  const { slug } = await params;
  const path = `/w/${slug}/settings/integrations`;
  await workspaceWith(slug, "workspace.update", path);
  const status = requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/integrations", { params: { path: { slug } } })),
    path,
  );
  return (
    <section aria-labelledby="integrations-heading" className="flex flex-col gap-4">
      <h2 id="integrations-heading" className="text-lg font-medium">
        Integrations
      </h2>
      <p className="text-muted-foreground text-sm">
        Which channels can receive and send messages. Onyx support connects WhatsApp numbers and
        email; contact them to add one.
      </p>
      <IntegrationList status={status} />
    </section>
  );
}
