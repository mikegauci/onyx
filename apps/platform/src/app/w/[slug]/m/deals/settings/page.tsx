import { notFound } from "next/navigation";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

import { DealSettingsForm } from "./settings-form";

type Props = { params: Promise<{ slug: string }> };

export default async function DealSettingsPage({ params }: Props) {
  const { slug } = await params;
  const path = dealsPath(slug, "settings");
  const workspace = requireOk(await getWorkspace(slug), path);
  if (!workspace.permissions.includes("deals.manage")) notFound();
  const settings = requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/deals/settings", { params: { path: { slug } } })),
    path,
  );
  return (
    <section
      aria-labelledby="deal-settings-heading"
      className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
    >
      <h2 id="deal-settings-heading" className="text-base font-medium tracking-tight">
        Document checklist
      </h2>
      <p className="text-muted-foreground text-sm">
        New deals start with these documents. “Only when” adds an item only to financed deals, deals
        with a trade-in, or once a deposit is recorded. Existing deals keep their list.
      </p>
      <DealSettingsForm slug={slug} settings={settings} />
    </section>
  );
}
