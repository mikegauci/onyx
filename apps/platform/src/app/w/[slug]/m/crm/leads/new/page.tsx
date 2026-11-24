import { crmPath } from "@/lib/crm";
import { workspaceWith } from "@/lib/settings-guard";
import { LeadForm } from "../../_components/forms";
import { contactOptions, param, type SearchParams } from "../../data";
import { getMe } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import Link from "next/link";
export default async function NewLeadPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = crmPath(slug, "leads", "new");
  await workspaceWith(slug, "crm.write", path);
  const contacts = await contactOptions(slug);
  const me = requireOk(await getMe(), path);
  const contactId = param((await searchParams).contact_id);
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-light tracking-tight">New lead</h2>
      {contacts.length > 0 ? (
        <div className="bg-card max-w-2xl rounded-2xl border p-5 sm:p-6">
          <LeadForm slug={slug} contacts={contacts} contactId={contactId} me={me.user.id} />
        </div>
      ) : (
        <p className="text-muted-foreground rounded-2xl border border-dashed px-5 py-4 text-sm">
          Create a contact before adding a lead.
        </p>
      )}
      <Link
        className="text-brand text-sm underline-offset-4 hover:underline"
        href={crmPath(slug, "contacts", "new")}
      >
        New contact
      </Link>
    </section>
  );
}
