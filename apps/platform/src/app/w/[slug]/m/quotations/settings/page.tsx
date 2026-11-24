import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { quotationsPath } from "@/lib/quotations";
import { workspaceWith } from "@/lib/settings-guard";

import { SettingsForm } from "../_components/forms";

export default async function QuotationSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const path = quotationsPath(slug, "settings");
  await workspaceWith(slug, "quotations.manage", path);
  const settings = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/quotations/settings", { params: { path: { slug } } }),
    ),
    path,
  );
  return (
    <section className="flex flex-col gap-4" aria-labelledby="settings-heading">
      <h2 id="settings-heading" className="text-lg font-light tracking-tight">
        Quotation settings
      </h2>
      <div className="bg-card max-w-2xl rounded-2xl border p-5 sm:p-6">
        <SettingsForm slug={slug} settings={settings} />
      </div>
      <p className="text-muted-foreground text-xs">
        Changes apply to new quotes and lines; approved versions keep what they were approved with.
      </p>
    </section>
  );
}
