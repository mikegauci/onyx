import { crmPath } from "@/lib/crm";
import { workspaceWith } from "@/lib/settings-guard";
import { ContactForm } from "../../_components/forms";
import { customerOptions } from "../../data";
export default async function NewContactPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = crmPath(slug, "contacts", "new");
  await workspaceWith(slug, "crm.write", path);
  const customers = await customerOptions(slug);
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium">New contact</h2>
      <ContactForm slug={slug} customers={customers} />
    </section>
  );
}
