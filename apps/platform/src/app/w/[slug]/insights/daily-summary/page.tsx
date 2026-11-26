import { Badge } from "@onyx/ui/components/badge";
import { PageHeader, Panel } from "@onyx/ui/components/page";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { reasonText, statusLabel, type SummaryHistoryItem } from "@/lib/daily-summary";
import { requireOk } from "@/lib/guards";
import { formatDay } from "@/lib/reminders";
import { workspaceWith } from "@/lib/settings-guard";

import { SummarySettingsForm, type TemplateOption, TestButton } from "./summary-forms";

const STATUS_VARIANT: Record<string, "success" | "warning" | "outline" | "secondary"> = {
  sent: "success",
  partly_sent: "warning",
  failed: "secondary",
  sending: "outline",
};

export default async function DailySummaryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = `/w/${slug}/insights/daily-summary`;
  await workspaceWith(slug, "workspace.update", path);
  const [settings, preview, history] = await Promise.all([
    withApi((api) =>
      api.GET("/v1/w/{slug}/insights/daily-summary/settings", { params: { path: { slug } } }),
    ).then((r) => requireOk(r, path)),
    withApi((api) =>
      api.GET("/v1/w/{slug}/insights/daily-summary/preview", { params: { path: { slug } } }),
    ).then((r) => requireOk(r, path)),
    withApi((api) =>
      api.GET("/v1/w/{slug}/insights/daily-summary/history", { params: { path: { slug } } }),
    ).then((r) => requireOk(r, path)),
  ]);
  const templates = await utilityTemplates(slug);

  return (
    <>
      <PageHeader
        eyebrow={<Link href={`/w/${slug}/insights`}>Insights</Link>}
        title="Daily summary"
        description="One message a day with the enquiries, cars reserved and sold, payments recorded and listing changes. Counts and amounts only: no customer names, numbers or messages."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Settings" divided={false}>
          <SummarySettingsForm slug={slug} settings={settings} templates={templates} />
        </Panel>
        <div className="flex flex-col gap-6">
          <Panel
            title="Today so far"
            description="What the summary would say now. A source that is not set up shows as missing, not as zero."
            divided={false}
          >
            <div className="flex flex-col gap-4">
              <pre className="bg-muted rounded-xl px-4 py-3 font-sans text-sm whitespace-pre-wrap">
                {preview.text}
              </pre>
              <TestButton slug={slug} />
            </div>
          </Panel>
          <Panel title="Sent" description="The last 30 days.">
            {history.items.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing sent yet.</p>
            ) : (
              <ul className="divide-y">
                {history.items.map((item) => (
                  <HistoryRow key={item.id} item={item} settings={settings} />
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

function HistoryRow({
  item,
  settings,
}: {
  item: SummaryHistoryItem;
  settings: { members: { user_id: string; display_name: string }[] };
}) {
  const names = new Map(settings.members.map((m) => [m.user_id, m.display_name]));
  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">{formatDay(item.summary_date)}</span>
        <Badge variant={STATUS_VARIANT[item.status] ?? "outline"}>{statusLabel(item.status)}</Badge>
      </div>
      <details className="text-sm">
        <summary className="text-muted-foreground cursor-pointer">Show message</summary>
        <pre className="bg-muted mt-2 rounded-xl px-4 py-3 font-sans whitespace-pre-wrap">
          {item.text}
        </pre>
      </details>
      <ul className="text-muted-foreground text-sm">
        {item.results.map((r, i) => (
          <li key={i}>
            {(r.user_id && names.get(r.user_id)) ?? "Former member"} ·{" "}
            {r.channel === "email" ? "Email" : "WhatsApp"}:{" "}
            {r.status === "sent" ? "sent" : reasonText(r.reason)}
          </li>
        ))}
      </ul>
    </li>
  );
}

async function utilityTemplates(slug: string): Promise<TemplateOption[]> {
  const channels = await withApi((api) =>
    api.GET("/v1/w/{slug}/inbox/channels", { params: { path: { slug } } }),
  );
  const whatsapp = channels.ok ? channels.data.items.filter((c) => c.kind === "whatsapp") : [];
  const lists = await Promise.all(
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
  );
  return lists.flat();
}
