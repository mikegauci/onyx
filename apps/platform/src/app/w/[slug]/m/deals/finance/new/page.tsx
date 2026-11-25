import { notFound } from "next/navigation";

import { BackLink } from "@/components/back-link";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

import { contactOptions } from "../../../crm/data";
import { NewApplicationForm } from "../../_components/finance-forms";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function NewFinancePage({ params, searchParams }: Props) {
  const { slug } = await params;
  const query = await searchParams;
  const dealId = typeof query.deal_id === "string" ? query.deal_id : "";
  const workspace = requireOk(await getWorkspace(slug), dealsPath(slug, "finance", "new"));
  if (!workspace.permissions.includes("deals.write")) notFound();
  const contacts = dealId ? [] : await contactOptions(slug);
  return (
    <>
      <BackLink href={dealId ? dealsPath(slug, dealId) : dealsPath(slug, "finance")}>
        {dealId ? "Back to the deal" : "Back to finance"}
      </BackLink>
      <section
        aria-labelledby="new-fin-heading"
        className="bg-card flex max-w-2xl flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="new-fin-heading" className="text-base font-medium tracking-tight">
          New finance application
        </h2>
        <p className="text-muted-foreground text-sm">
          Onyx works out the estimate and the documents the customer needs. Ventur&apos;s finance
          team decides; record the decision here once it is made.
        </p>
        <NewApplicationForm
          slug={slug}
          contacts={contacts}
          dealId={dealId}
          canManage={workspace.permissions.includes("finance.manage")}
        />
      </section>
    </>
  );
}
