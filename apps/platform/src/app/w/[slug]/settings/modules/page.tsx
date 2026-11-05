import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { ModulesTable } from "./modules-table";

type Props = { params: Promise<{ slug: string }> };

export default async function ModulesSettingsPage({ params }: Props) {
  const { slug } = await params;
  const path = `/w/${slug}/settings/modules`;
  const workspace = await workspaceWith(slug, "workspace.update", path);
  const modules = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules", { params: { path: { slug: workspace.slug } } }),
    ),
    path,
  );
  return (
    <section aria-labelledby="modules-heading" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="modules-heading" className="text-lg font-medium">
          Modules
        </h2>
        <p className="text-muted-foreground text-sm">
          Modules are part of your plan and are enabled by Onyx. Contact us to change them.
        </p>
      </div>
      <ModulesTable modules={modules} />
    </section>
  );
}
