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

import { ChannelForm, ChannelToggle } from "../_components/forms";

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
                  <ChannelToggle slug={slug} channel={channel} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      <section className="flex flex-col gap-4" aria-labelledby="new-channel-heading">
        <h2 id="new-channel-heading" className="text-lg font-medium">
          Add a channel
        </h2>
        <ChannelForm slug={slug} />
      </section>
    </div>
  );
}
