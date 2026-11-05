import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";
import { quotationsPath } from "@/lib/quotations";
import { workspaceWith } from "@/lib/settings-guard";

import { contactOptions } from "../../../crm/data";
import { NewQuoteForm } from "../../_components/forms";

export default async function NewQuotePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = quotationsPath(slug, "quotes", "new");
  await workspaceWith(slug, "quotations.write", path);
  const [contacts, leads] = await Promise.all([
    contactOptions(slug),
    withApi((api) =>
      api.GET("/v1/w/{slug}/crm/leads", { params: { path: { slug }, query: { limit: 100 } } }),
    ),
  ]);
  const leadOptions = requireOk(leads, path).items.map((lead) => ({
    id: lead.id,
    label: `${lead.title} (${lead.contact.full_name})`,
  }));

  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm underline" href={quotationsPath(slug, "quotes")}>
        Back to quotes
      </Link>
      <h2 className="text-xl font-medium">New quote</h2>
      {contacts.length === 0 ? (
        <p className="text-muted-foreground text-sm">Add a CRM contact before drafting a quote.</p>
      ) : (
        <NewQuoteForm slug={slug} contacts={contacts} leads={leadOptions} />
      )}
    </div>
  );
}
