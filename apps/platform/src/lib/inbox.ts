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
