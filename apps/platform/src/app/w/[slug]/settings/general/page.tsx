import { workspaceWith } from "@/lib/settings-guard";

import { GeneralForm } from "./general-form";

type Props = { params: Promise<{ slug: string }> };

export default async function GeneralSettingsPage({ params }: Props) {
  const { slug } = await params;
  const workspace = await workspaceWith(slug, "workspace.update", `/w/${slug}/settings/general`);
  const timezones = Intl.supportedValuesOf("timeZone");
  if (!timezones.includes(workspace.timezone)) timezones.unshift(workspace.timezone);

  return (
    <section aria-labelledby="general-heading" className="flex max-w-lg flex-col gap-4">
      <h2 id="general-heading" className="text-lg font-medium">
        General
      </h2>
      <GeneralForm
        slug={workspace.slug}
        name={workspace.name}
        timezone={workspace.timezone}
        timezones={timezones}
      />
    </section>
  );
}
