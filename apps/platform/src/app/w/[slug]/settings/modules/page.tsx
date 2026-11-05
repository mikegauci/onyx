import { EmptyState } from "@onyx/ui/components/states";
import { Blocks } from "lucide-react";

import { workspaceWith } from "@/lib/settings-guard";

type Props = { params: Promise<{ slug: string }> };

export default async function ModulesSettingsPage({ params }: Props) {
  const { slug } = await params;
  await workspaceWith(slug, "workspace.update", `/w/${slug}/settings/modules`);
  return (
    <section aria-labelledby="modules-heading" className="flex flex-col gap-4">
      <h2 id="modules-heading" className="text-lg font-medium">
        Modules
      </h2>
      <EmptyState
        icon={Blocks}
        title="Coming soon"
        description="Enable or disable modules for this workspace. Arrives with module entitlements (PR-008)."
      />
    </section>
  );
}
