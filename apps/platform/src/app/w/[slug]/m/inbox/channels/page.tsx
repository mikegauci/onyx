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
import { CHANNEL_KIND_LABEL, inboxPath } from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { ChannelForm, ChannelToggle, CopyAddress, EmailSettingsForm } from "../_components/forms";

export default async function ChannelsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = inboxPath(slug, "channels");
  await workspaceWith(slug, "inbox.manage", path);
  const channels = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/channels", {
        params: { path: { slug }, query: { include_disabled: true } },
      }),
    ),
    path,
  ).items;
  const emailChannels = channels.filter((c) => c.kind === "email" && c.disabled_at === null);

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
                  {channel.kind !== "email" ? (
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
      <section className="flex flex-col gap-4" aria-labelledby="new-channel-heading">
        <h2 id="new-channel-heading" className="text-lg font-medium">
          Add a channel
        </h2>
        <ChannelForm slug={slug} />
      </section>
    </div>
  );
}
