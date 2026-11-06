/** Display metadata for module keys. Entitlements come from the API, never from here. */
export const MODULES: Record<string, { label: string; arrives: string }> = {
  crm: { label: "CRM", arrives: "PR-009" },
  catalogue: { label: "Catalogue", arrives: "PR-010" },
  inbox: { label: "Inbox", arrives: "PR-011" },
  quotations: { label: "Quotations", arrives: "PR-012" },
  orders: { label: "Orders", arrives: "PR-022" },
  assistant: { label: "Sales assistant", arrives: "PR-015" },
  outbound: { label: "Outbound replies", arrives: "PR-016" },
};

export function moduleLabel(key: string): string {
  return MODULES[key]?.label ?? key;
}
