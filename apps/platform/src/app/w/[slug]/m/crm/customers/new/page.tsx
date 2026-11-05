import { crmPath } from "@/lib/crm";
import { workspaceWith } from "@/lib/settings-guard";
import { CustomerForm } from "../../_components/forms";

export default async function NewCustomerPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = crmPath(slug, "customers", "new");
  await workspaceWith(slug, "crm.write", path);

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium">New customer</h2>
      <CustomerForm slug={slug} />
    </section>
  );
}
