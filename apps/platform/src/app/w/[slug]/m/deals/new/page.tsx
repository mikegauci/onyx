import { notFound } from "next/navigation";

import { BackLink } from "@/components/back-link";
import { withApi } from "@/lib/api-client";
import { euros } from "@/lib/automotive";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

import { contactOptions } from "../../crm/data";
import { NewDealForm } from "./new-deal-form";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const one = (value: string | string[] | undefined) => (typeof value === "string" ? value : "");

export default async function NewDealPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const query = await searchParams;
  const path = dealsPath(slug, "new");
  const workspace = requireOk(await getWorkspace(slug), path);
  if (!workspace.permissions.includes("deals.write")) notFound();
  const contacts = await contactOptions(slug);
  // Available cars only; the API refuses a car that is sold or held by another deal.
  const vehicles = workspace.modules.includes("automotive")
    ? requireOk(
        await withApi((api) =>
          api.GET("/v1/w/{slug}/automotive/vehicles", {
            params: { path: { slug }, query: { status: "available" } },
          }),
        ),
        path,
      ).items.map((v) => ({
        id: v.id,
        label: `${v.title}${v.stock_number ? ` (${v.stock_number})` : ""} · ${euros(v.price_cents)}`,
      }))
    : null;

  return (
    <>
      <BackLink href={dealsPath(slug, "board")}>Back to deals</BackLink>
      <section
        aria-labelledby="new-deal-heading"
        className="bg-card flex max-w-2xl flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="new-deal-heading" className="text-base font-medium tracking-tight">
          New deal
        </h2>
        <p className="text-muted-foreground text-sm">
          A deal follows one sale. Reserving a car here marks it reserved, so the assistant stops
          offering it.
        </p>
        <NewDealForm
          slug={slug}
          contacts={contacts}
          vehicles={vehicles}
          defaults={{
            contactId: one(query.contact_id),
            quoteId: one(query.quote_id),
            leadId: one(query.lead_id),
            conversationId: one(query.conversation_id),
          }}
        />
      </section>
    </>
  );
}
