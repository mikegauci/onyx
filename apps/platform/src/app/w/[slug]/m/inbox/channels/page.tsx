import { Badge } from "@onyx/ui/components/badge";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { formatInZone } from "@/lib/crm";
import {
  CHANNEL_KIND_LABEL,
  inboxPath,
  templateUnusableReason,
  type WhatsAppTemplate,
} from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { ChannelForm, ChannelToggle, CopyAddress, EmailSettingsForm } from "../_components/forms";
import { SyncTemplatesButton } from "../_components/whatsapp";

export default async function ChannelsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = inboxPath(slug, "channels");
  const workspace = await workspaceWith(slug, "inbox.manage", path);
  const channels = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/channels", {
        params: { path: { slug }, query: { include_disabled: true } },
      }),
    ),
    path,
  ).items;
  const emailChannels = channels.filter((c) => c.kind === "email" && c.disabled_at === null);
  const whatsappChannels = channels.filter(
    (c) => c.kind === "whatsapp" && c.disabled_at === null && c.phone_number,
  );
  const templates = await Promise.all(
    whatsappChannels.map(async (channel) => ({
      channel,
      items: requireOk(
        await withApi((api) =>
          api.GET("/v1/w/{slug}/inbox/channels/{channel_id}/whatsapp-templates", {
            params: { path: { slug, channel_id: channel.id } },
          }),
        ),
        path,
      ).items,
    })),
  );

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4" aria-labelledby="channels-heading">
        <h2 id="channels-heading" className="text-lg font-medium">
          Channels
        </h2>
        <Table>
          <TableCaption className="sr-only">Channels</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Customers write to</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {channels.map((channel) => (
              <TableRow key={channel.id}>
                <TableCell className="font-medium">{channel.name}</TableCell>
                <TableCell>{CHANNEL_KIND_LABEL[channel.kind]}</TableCell>
                <TableCell>
                  {channel.disabled_at ? (
                    <Badge variant="outline">Disabled</Badge>
                  ) : channel.connected ? (
                    <Badge variant="success">Active</Badge>
                  ) : (
                    <Badge variant="warning">Not connected yet</Badge>
                  )}
                </TableCell>
                <TableCell>
                  {channel.kind === "whatsapp" ? (
                    channel.phone_number ? (
                      <span className="text-sm">WhatsApp {channel.phone_number}</span>
                    ) : (
                      <span className="text-muted-foreground text-sm">
                        Onyx support connects the business number
                      </span>
                    )
                  ) : channel.kind !== "email" ? (
                    <span className="text-muted-foreground text-sm">—</span>
                  ) : channel.inbound_address ? (
                    <CopyAddress address={channel.inbound_address} />
                  ) : (
                    <span className="text-muted-foreground text-sm">
                      Shown once email is connected
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <ChannelToggle slug={slug} channel={channel} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      {emailChannels.length > 0 ? (
        <section className="flex flex-col gap-4" aria-labelledby="email-settings-heading">
          <h2 id="email-settings-heading" className="text-lg font-medium">
            Email sender details
          </h2>
          <p className="text-muted-foreground text-sm">
            Forward your shop mailbox to the channel&apos;s address, or give it to customers.
            Approved replies are emailed from Onyx with this name and signature, and the
            customer&apos;s answer comes back to the same conversation.
          </p>
          {emailChannels.map((channel) => (
            <div key={channel.id} className="flex flex-col gap-2 rounded-md border p-3">
              <h3 className="font-medium">{channel.name}</h3>
              <EmailSettingsForm slug={slug} channel={channel} />
            </div>
          ))}
        </section>
      ) : null}
      {templates.length > 0 ? (
        <section className="flex flex-col gap-4" aria-labelledby="templates-heading">
          <h2 id="templates-heading" className="text-lg font-medium">
            WhatsApp templates
          </h2>
          <p className="text-muted-foreground text-sm">
            More than 24 hours after the customer&apos;s last message, WhatsApp only allows
            templates approved by Meta. Create them in WhatsApp Manager, then refresh the list here.
          </p>
          {templates.map(({ channel, items }) => (
            <div key={channel.id} className="flex flex-col gap-3 rounded-md border p-3">
              <h3 className="font-medium">
                {channel.name} · {channel.phone_number}
              </h3>
              <TemplateTable items={items} name={channel.name} zone={workspace.timezone} />
              <SyncTemplatesButton slug={slug} channelId={channel.id} channelName={channel.name} />
            </div>
          ))}
        </section>
      ) : null}
      <section className="flex flex-col gap-4" aria-labelledby="new-channel-heading">
        <h2 id="new-channel-heading" className="text-lg font-medium">
          Add a channel
        </h2>
        <ChannelForm slug={slug} />
      </section>
    </div>
  );
}

function TemplateTable({
  items,
  name,
  zone,
}: {
  items: WhatsAppTemplate[];
  name: string;
  zone: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm">No templates yet. Refresh to fetch them from WhatsApp.</p>;
  }
  return (
    <Table>
      <TableCaption className="sr-only">Templates for {name}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Template</TableHead>
          <TableHead>Category</TableHead>
          <TableHead>Can be sent</TableHead>
          <TableHead>Checked</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((t) => {
          const reason = templateUnusableReason(t);
          return (
            <TableRow key={t.id}>
              <TableCell>
                <p className="font-medium">
                  {t.name} <span className="text-muted-foreground">({t.language})</span>
                </p>
                {t.body ? (
                  <p className="text-muted-foreground max-w-md text-xs whitespace-pre-wrap">
                    {t.body}
                  </p>
                ) : null}
              </TableCell>
              <TableCell className="capitalize">{t.category}</TableCell>
              <TableCell>
                {reason ? (
                  <div className="flex flex-col gap-1">
                    <Badge variant="outline">No</Badge>
                    <span className="text-muted-foreground text-xs">{reason}</span>
                  </div>
                ) : (
                  <Badge variant="success">Yes</Badge>
                )}
              </TableCell>
              <TableCell className="text-sm">
                <time dateTime={t.synced_at}>{formatInZone(t.synced_at, zone)}</time>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
