import { EmptyState } from "@onyx/ui/components/states";
import { Construction } from "lucide-react";
import { notFound } from "next/navigation";

import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { MODULES, moduleLabel } from "@/lib/modules";

type Props = { params: Promise<{ slug: string; module: string }> };

export default async function ModulePage({ params }: Props) {
  const { slug, module } = await params;
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}/m/${module}`);
  // Display only: PR-008 enforces module entitlements in the API.
  if (!workspace.modules.includes(module)) notFound();

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">{moduleLabel(module)}</h1>
      <EmptyState
        icon={Construction}
        title={`${moduleLabel(module)} is on its way`}
        description={`This module arrives in ${MODULES[module]?.arrives ?? "a later release"}.`}
      />
    </>
  );
}
