/** Display metadata for module keys. Entitlements come from the API, never from here. */
export const MODULES: Record<string, { label: string; arrives: string; blurb: string }> = {
  crm: { label: "CRM", arrives: "PR-009", blurb: "Leads, contacts and customers." },
  catalogue: { label: "Catalogue", arrives: "PR-010", blurb: "Products, prices and stock." },
  inbox: { label: "Inbox", arrives: "PR-011", blurb: "WhatsApp, email and calls in one queue." },
  quotations: { label: "Quotations", arrives: "PR-012", blurb: "Draft, approve and send quotes." },
  orders: { label: "Orders", arrives: "PR-022", blurb: "Orders and fulfilment." },
  assistant: {
    label: "Sales assistant",
    arrives: "PR-015",
    blurb: "AI drafts replies from your own data.",
  },
  outbound: {
    label: "Outbound replies",
    arrives: "PR-016",
    blurb: "Replies waiting for approval.",
  },
  knowledge: {
    label: "Knowledge",
    arrives: "PR-014 part 2",
    blurb: "Documents the assistant can quote.",
  },
  automotive: {
    label: "Vehicles",
    arrives: "VA-001 part 2",
    blurb: "Stock imported from your site.",
  },
  deals: {
    label: "Deals",
    arrives: "VA-007",
    blurb: "Sales from reservation to collection, with documents.",
  },
};

export function moduleLabel(key: string): string {
  return MODULES[key]?.label ?? key;
}
