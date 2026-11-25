import { Panel } from "@onyx/ui/components/page";

import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { AlertSettingsForm } from "../_components/alerts";

export default async function AlertSettingsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = automotivePath(slug, "alerts");
  await workspaceWith(slug, "inbox.manage", path);
  const settings = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/alert-settings", { params: { path: { slug } } }),
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
              .filter((t) => t.category === "marketing" && t.status === "approved")
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
    <Panel title="Car alerts" divided={false}>
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground max-w-prose text-sm">
          The WhatsApp message sent when a new car matches what a buyer wants. WhatsApp only allows
          an approved <strong>marketing</strong> template for this, and Onyx only sends it to
          customers who agreed to car alerts. Meta charges for each marketing conversation.
        </p>
        {templates.length === 0 ? (
          <p className="text-sm">
            No approved marketing template yet. Create one in WhatsApp Manager, then sync templates
            on the WhatsApp channel in Inbox.
          </p>
        ) : null}
        <AlertSettingsForm slug={slug} settings={settings} templates={templates} />
      </div>
    </Panel>
  );
}
