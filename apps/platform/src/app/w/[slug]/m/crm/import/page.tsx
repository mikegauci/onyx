import { crmPath } from "@/lib/crm";
import { workspaceWith } from "@/lib/settings-guard";
import { ImportForm } from "./import-form";

export default async function ImportPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  await workspaceWith(slug, "crm.import", crmPath(slug, "import"));
  return (
    <section className="flex max-w-3xl flex-col gap-4">
      <h2 className="text-lg font-light tracking-tight">Import contacts</h2>
      <p className="text-muted-foreground text-sm">
        Upload a UTF-8 CSV, up to 1 MB and 2,000 rows. Include full_name and an email or phone for
        each contact. Optional columns: company, notes, lead_title. A lead title creates a new lead.
      </p>
      <a
        className="text-brand text-sm underline-offset-4 hover:underline"
        href="/examples/crm-contacts.csv"
        download
      >
        Download example CSV
      </a>
      <p className="text-sm">
        Preview first, then import valid rows. Invalid rows and duplicate contacts are skipped.
        Existing contacts are never overwritten.
      </p>
      <div className="bg-card rounded-2xl border p-5 sm:p-6">
        <ImportForm slug={slug} />
      </div>
    </section>
  );
}
