import "server-only";
import { notFound } from "next/navigation";
import { withApi } from "@/lib/api-client";
import { crmPath, type Contact, type Customer } from "@/lib/crm";
import { requireOk } from "@/lib/guards";

export type SearchParams = Promise<Record<string, string | string[] | undefined>>;
export function param(value: string | string[] | undefined, max = 200): string | undefined {
  return typeof value === "string" ? value.slice(0, max) || undefined : undefined;
}
export function recordId(value: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) notFound();
  return value;
}
// Fetch every page so older records remain selectable on creation and edit forms.
export async function customerOptions(slug: string) {
  const items: Customer[] = [];
  let cursor: string | undefined;
  do {
    const page = requireOk(
      await withApi((api) =>
        api.GET("/v1/w/{slug}/crm/customers", {
          params: { path: { slug }, query: { limit: 100, cursor } },
        }),
      ),
      crmPath(slug),
    );
    items.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return items.map((c) => ({ id: c.id, label: c.name }));
}
export async function contactOptions(slug: string) {
  const items: Contact[] = [];
  let cursor: string | undefined;
  do {
    const page = requireOk(
      await withApi((api) =>
        api.GET("/v1/w/{slug}/crm/contacts", {
          params: { path: { slug }, query: { limit: 100, cursor } },
        }),
      ),
      crmPath(slug),
    );
    items.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return items.map((c) => ({ id: c.id, label: c.full_name }));
}
