import { EmptyState } from "@onyx/ui/components/states";
import { Construction } from "lucide-react";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { MODULES, moduleLabel } from "@/lib/modules";

type Props = { params: Promise<{ slug: string; module: string }> };

export default async function ModulePage({ params }: Props) {
  const { slug, module } = await params;
  // The API decides: a disabled or unknown module is 403/404, shown as the not-found page.
  const status = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/modules/{key}", { params: { path: { slug, key: module } } }),
    ),
    `/w/${slug}/m/${module}`,
  );

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">{status.name}</h1>
      <EmptyState
        icon={Construction}
        title={`${moduleLabel(status.key)} is on its way`}
        description={`This module arrives in ${MODULES[status.key]?.arrives ?? "a later release"}.`}
      />
    </>
  );
}
