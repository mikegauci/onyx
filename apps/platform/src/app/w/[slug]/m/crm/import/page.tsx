import { crmPath } from "@/lib/crm";
import { workspaceWith } from "@/lib/settings-guard";
import { ImportForm } from "./import-form";

export default async function ImportPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  await workspaceWith(slug, "crm.import", crmPath(slug, "import"));
  return (
    <section className="flex max-w-3xl flex-col gap-4">
      <h2 className="text-lg font-medium">Import contacts</h2>
      <p className="text-muted-foreground text-sm">
        Upload a UTF-8 CSV, up to 1 MB and 2,000 rows. Include full_name and an email or phone for
        each contact. Optional columns: company, notes, lead_title. A lead title creates a new lead.
      </p>
      <a className="text-sm underline" href="/examples/crm-contacts.csv" download>
        Download example CSV
      </a>
      <p className="text-sm">
        Preview first, then import valid rows. Invalid rows and duplicate contacts are skipped.
        Existing contacts are never overwritten.
      </p>
      <ImportForm slug={slug} />
    </section>
  );
}
