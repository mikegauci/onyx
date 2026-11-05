import { withApi } from "@/lib/api-client";
import { cataloguePath } from "@/lib/catalogue";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { CatalogueImportForm } from "./import-form";

export default async function CatalogueImportPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const path = cataloguePath(slug, "import");
  await workspaceWith(slug, "catalogue.import", path);
  const priceLists = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/catalogue/price-lists", { params: { path: { slug } } }),
    ),
    path,
  ).items;
  return (
    <section className="flex max-w-3xl flex-col gap-4">
      <h2 className="text-lg font-medium">Import catalogue</h2>
      <p className="text-muted-foreground text-sm">
        Upload a UTF-8 CSV, up to 2 MB and 5,000 rows, one row per SKU. Required columns: sku,
        product_code, product_name. Optional: variant_name, brand, category, description, vat_code,
        price_eur (e.g. 24.90), stock_available, stock_location, stock_observed_at (ISO 8601 with a
        time zone) and attr_&lt;name&gt; columns for attributes.
      </p>
      <a className="text-sm underline" href="/examples/catalogue.csv" download>
        Download example CSV
      </a>
      <p className="text-sm">
        Preview first, then import valid rows. Blank cells are treated as “not provided”: they never
        clear stored data or count as zero. A stock figure needs an as-of time, from its row or the
        export time below. Prices are valid from the export time, or from the import.
      </p>
      <CatalogueImportForm slug={slug} priceLists={priceLists} />
    </section>
  );
}
