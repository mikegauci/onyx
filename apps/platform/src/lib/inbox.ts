/** Display helpers for the inbox. Status, handoff and assignment rules live in the API. */
import type { components } from "@onyx/api-client";

export type ConversationSummary = components["schemas"]["ConversationSummary"];
export type ConversationDetail = components["schemas"]["ConversationDetail"];
export type ConversationStatus = components["schemas"]["ConversationStatus"];
export type Message = components["schemas"]["MessageOut"];
export type InboxEvent = components["schemas"]["EventOut"];
export type Channel = components["schemas"]["ChannelOut"];
export type Assignee = components["schemas"]["Assignee"];

export function inboxPath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/inbox`, ...parts].join("/");
}

export const STATUS_LABEL: Record<ConversationStatus, string> = {
  open: "Open",
  waiting_on_customer: "Waiting on customer",
  closed: "Closed",
};

export const STATUS_VARIANT: Record<ConversationStatus, "default" | "outline" | "secondary"> = {
  open: "default",
  waiting_on_customer: "secondary",
  closed: "outline",
};

export const STATUS_ACTION: Record<ConversationStatus, string> = {
  open: "Reopen",
  waiting_on_customer: "Mark waiting on customer",
  closed: "Close",
};

export const QUEUES = [
  { key: "mine", label: "Mine" },
  { key: "unassigned", label: "Unassigned" },
  { key: "all", label: "All" },
] as const;
export type Queue = (typeof QUEUES)[number]["key"];

export const CHANNEL_KIND_LABEL: Record<Channel["kind"], string> = {
  manual: "Phone / in person",
  email: "Email",
  whatsapp: "WhatsApp",
  web: "Website",
};

export function messageHeading(message: Message): string {
  if (message.direction === "note") {
    if (message.author_kind === "assistant") return "Internal note by Assistant";
    return `Internal note by ${message.author?.display_name ?? "a former member"}`;
  }
  if (message.direction === "inbound") {
    const who =
      message.participant?.contact?.full_name ??
      message.participant?.display_name ??
      message.participant?.address ??
      "Customer";
    return `${who} (customer)`;
  }
  const by =
    message.author?.display_name ?? (message.author_kind === "assistant" ? "Assistant" : "Staff");
  return message.delivery_status === "logged" ? `Reply logged by ${by}` : `Reply by ${by}`;
}

const EVENT_LABEL: Record<InboxEvent["kind"], string> = {
  created: "Conversation started",
  assigned: "Assigned",
  unassigned: "Unassigned",
  status_changed: "Status changed",
  handed_to_staff: "Handed to staff",
  handed_to_assistant: "Handed to the assistant",
  contact_linked: "Contact linked",
  lead_linked: "Lead linked",
  subject_changed: "Subject changed",
};

export function describeEvent(event: InboxEvent): string {
  const label = EVENT_LABEL[event.kind];
  if (event.kind === "status_changed") {
    const to = event.details.to as ConversationStatus | undefined;
    const why = event.details.reason === "customer_message" ? " (customer wrote again)" : "";
    return to ? `${label} to ${STATUS_LABEL[to].toLowerCase()}${why}` : label;
  }
  return label;
}

export type Suppression = components["schemas"]["SuppressionOut"];
export type EmailDelivery = components["schemas"]["EmailDeliveryOut"];
export type EmailDeliveryStatus = components["schemas"]["EmailDeliveryStatus"];
export type ComposeKind = "reply" | "customer" | "note";

/**
 * What staff may record by hand on a channel. On email, replies leave only through an approved
 * draft, so "Log a reply" is not offered; the API refuses it (409) whatever the screen shows.
 */
export function composeKinds(channelKind: Channel["kind"]): ComposeKind[] {
  return channelKind === "email" ? ["customer", "note"] : ["reply", "customer", "note"];
}

export const DELIVERY_LABEL: Record<EmailDeliveryStatus, string> = {
  sent: "Sent",
  delayed: "Delayed",
  delivered: "Delivered",
  bounced: "Bounced",
  complained: "Marked as spam",
  failed: "Failed",
  suppressed: "Not sent: address blocked",
};

export const DELIVERY_VARIANT: Record<
  EmailDeliveryStatus,
  "info" | "warning" | "success" | "destructive"
> = {
  sent: "info",
  delayed: "warning",
  delivered: "success",
  bounced: "destructive",
  complained: "destructive",
  failed: "destructive",
  suppressed: "destructive",
};

/** Statuses after which the provider (or Onyx) blocks further email to the address. */
export function deliveryBlocksAddress(status: EmailDeliveryStatus): boolean {
  return status === "bounced" || status === "complained" || status === "suppressed";
}

export const SUPPRESSION_REASON_LABEL: Record<Suppression["reason"], string> = {
  bounced: "Bounced",
  complained: "Marked as spam",
  manual: "Added by staff",
};
