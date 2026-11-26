import { Panel } from "@onyx/ui/components/page";

import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { ReminderSettingsForm } from "../_components/reminders";

export default async function ReminderSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const path = automotivePath(slug, "reminder-settings");
  await workspaceWith(slug, "inbox.manage", path);
  const settings = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/reminder-settings", { params: { path: { slug } } }),
    ),
    path,
  );
  const channels = await withApi((api) =>
    api.GET("/v1/w/{slug}/inbox/channels", { params: { path: { slug } } }),
  );
  const whatsapp = channels.ok ? channels.data.items.filter((c) => c.kind === "whatsapp") : [];
  const templates = (
    await Promise.all(
      whatsapp.map(async (channel) => {
        const list = await withApi((api) =>
          api.GET("/v1/w/{slug}/inbox/channels/{channel_id}/whatsapp-templates", {
            params: { path: { slug, channel_id: channel.id } },
          }),
        );
        return list.ok
          ? list.data.items
              .filter((t) => t.usable)
              .map((t) => ({
                id: t.id,
                label: `${t.name} (${t.language}) · ${channel.name}`,
                paramCount: t.param_count,
                body: t.body,
              }))
          : [];
      }),
    )
  ).flat();
  return (
    <Panel title="Reminders" divided={false}>
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground max-w-prose text-sm">
          When each reminder appears in the Reminders list, and what it says. Nothing is sent
          automatically. Outside WhatsApp’s 24-hour window a reminder needs an approved{" "}
          <strong>utility</strong> template; without one it goes by email.
        </p>
        <ReminderSettingsForm slug={slug} settings={settings} templates={templates} />
      </div>
    </Panel>
  );
}
