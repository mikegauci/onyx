import { EmptyState } from "@onyx/ui/components/states";
import { CreditCard } from "lucide-react";

import { workspaceWith } from "@/lib/settings-guard";

type Props = { params: Promise<{ slug: string }> };

export default async function BillingSettingsPage({ params }: Props) {
  const { slug } = await params;
  await workspaceWith(slug, "workspace.update", `/w/${slug}/settings/billing`);
  return (
    <section aria-labelledby="billing-heading" className="flex flex-col gap-4">
      <h2 id="billing-heading" className="text-lg font-medium">
        Billing
      </h2>
      <EmptyState
        icon={CreditCard}
        title="Coming soon"
        description="Plan, invoices and AI usage. Arrives with Stripe Billing (PR-026)."
      />
    </section>
  );
}
