/** Display helpers for the CRM. Rules (statuses, transitions, permissions) come from the API. */
import type { components } from "@onyx/api-client";

export type Lead = components["schemas"]["LeadOut"];
export type LeadStatus = components["schemas"]["LeadStatus"];
export type Contact = components["schemas"]["ContactOut"];
export type Customer = components["schemas"]["CustomerOut"];
export type Activity = components["schemas"]["ActivityOut"];
export type ImportResult = components["schemas"]["ContactImportResult"];
export type SubjectType = components["schemas"]["SubjectType"];

export const LEAD_STATUSES: LeadStatus[] = ["new", "contacted", "qualified", "won", "lost"];

export const STATUS_LABEL: Record<LeadStatus, string> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  won: "Won",
  lost: "Lost",
};

export const STATUS_VARIANT: Record<
  LeadStatus,
  "info" | "secondary" | "brand" | "success" | "outline"
> = {
  new: "info",
  contacted: "secondary",
  qualified: "brand",
  won: "success",
  lost: "outline",
};

/** Verb for the button that moves a lead to `status`. */
export const STATUS_ACTION: Record<LeadStatus, string> = {
  new: "Reopen",
  contacted: "Mark contacted",
  qualified: "Mark qualified",
  won: "Mark won",
  lost: "Mark lost",
};

export function crmPath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/crm`, ...parts].join("/");
}

export function formatInZone(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(iso));
}

const FIELD_LABEL: Record<string, string> = {
  full_name: "name",
  customer_id: "customer",
  owner_user_id: "owner",
  vat_number: "VAT number",
};

/** One line describing an activity entry, from its kind and details (never contact values). */
export function describeActivity(activity: Activity): string {
  const details = activity.details as Record<string, unknown>;
  switch (activity.kind) {
    case "created":
      return details.source === "import" ? "Created from an import" : "Created";
    case "updated": {
      const fields = Array.isArray(details.fields) ? (details.fields as string[]) : [];
      return fields.length > 0
        ? `Updated ${fields.map((f) => FIELD_LABEL[f] ?? f.replaceAll("_", " ")).join(", ")}`
        : "Updated";
    }
    case "status_changed": {
      const from = STATUS_LABEL[details.from as LeadStatus] ?? String(details.from);
      const to = STATUS_LABEL[details.to as LeadStatus] ?? String(details.to);
      return `Status changed from ${from} to ${to}`;
    }
    case "note":
      return "Note";
    case "imported":
      return "Imported from CSV";
    case "archived":
      return "Archived";
    case "restored":
      return "Restored";
  }
}
