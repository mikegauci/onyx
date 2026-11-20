import { Badge } from "@onyx/ui/components/badge";

import { CHANNEL_KIND_LABEL } from "@/lib/inbox";
import type { IntegrationStatus } from "@/lib/tenants";

/** Each channel and whether it works, plus provider setup. No tokens or addresses. */
export function IntegrationList({ status }: { status: IntegrationStatus }) {
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1 text-sm" aria-label="Providers">
        <li>
          Email sending and receiving:{" "}
          {status.email_configured ? "set up by Onyx" : "not set up on this server yet"}
        </li>
        <li>
          WhatsApp Business:{" "}
          {status.whatsapp_configured ? "set up by Onyx" : "not set up on this server yet"}
        </li>
      </ul>
      {status.channels.length === 0 ? (
        <p className="text-sm">No channels yet. Add them under Inbox → Channels.</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Channels">
          {status.channels.map((c) => (
            <li
              key={c.id}
              className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm"
            >
              <span className="font-medium">{c.name}</span>
              <span className="text-muted-foreground">{CHANNEL_KIND_LABEL[c.kind]}</span>
              {c.phone_number ? <span>{c.phone_number}</span> : null}
              <span className="ml-auto">
                {c.disabled ? (
                  <Badge variant="outline">Disabled</Badge>
                ) : c.connected ? (
                  <Badge variant="success">Connected</Badge>
                ) : (
                  <Badge variant="warning">Not connected yet</Badge>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
