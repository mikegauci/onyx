import { workspaceWith } from "@/lib/settings-guard";

import { GeneralForm } from "./general-form";

type Props = { params: Promise<{ slug: string }> };

export default async function GeneralSettingsPage({ params }: Props) {
  const { slug } = await params;
  const workspace = await workspaceWith(slug, "workspace.update", `/w/${slug}/settings/general`);
  const timezones = Intl.supportedValuesOf("timeZone");
  if (!timezones.includes(workspace.timezone)) timezones.unshift(workspace.timezone);

  return (
    <section
      aria-labelledby="general-heading"
      className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
    >
      <h2 id="general-heading" className="text-base font-medium tracking-tight">
        General
      </h2>
      <GeneralForm
        slug={workspace.slug}
        name={workspace.name}
        timezone={workspace.timezone}
        timezones={timezones}
        displayName={workspace.display_name ?? ""}
        brandColor={workspace.brand_color ?? ""}
        currency={workspace.currency}
      />
    </section>
  );
}
