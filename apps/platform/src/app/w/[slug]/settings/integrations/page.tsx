import { EmptyState } from "@onyx/ui/components/states";
import { Plug } from "lucide-react";

import { workspaceWith } from "@/lib/settings-guard";

type Props = { params: Promise<{ slug: string }> };

export default async function IntegrationsSettingsPage({ params }: Props) {
  const { slug } = await params;
  await workspaceWith(slug, "workspace.update", `/w/${slug}/settings/integrations`);
  return (
    <section aria-labelledby="integrations-heading" className="flex flex-col gap-4">
      <h2 id="integrations-heading" className="text-lg font-medium">
        Integrations
      </h2>
      <EmptyState
        icon={Plug}
        title="Coming soon"
        description="Connect email, WhatsApp and inventory sources. Arrives with PR-017, PR-019 and PR-024."
      />
    </section>
  );
}
