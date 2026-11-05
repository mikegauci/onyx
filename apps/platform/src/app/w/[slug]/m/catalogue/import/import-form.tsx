"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useActionState, useState } from "react";

import type { PriceList } from "@/lib/catalogue";

import { FormStatus, SELECT_CLASS } from "../../../settings/form-status";
import { type CatalogueImportState, importCatalogue } from "../actions";

const INITIAL: CatalogueImportState = { status: "idle" };

/** The browser's local time from a datetime-local field, as ISO 8601 with its UTC offset. */
function toIso(local: string): string {
  if (!local) return "";
  const date = new Date(local);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

export function CatalogueImportForm({
  slug,
  priceLists,
}: {
  slug: string;
  priceLists: PriceList[];
}) {
  const [state, action, pending] = useActionState(importCatalogue.bind(null, slug), INITIAL);
  const [exportedAt, setExportedAt] = useState("");
  const result = state.result;
  const counts = result?.counts;
  const defaultList = priceLists.find((pl) => pl.is_default);
  return (
    <div className="flex flex-col gap-4">
      <FormStatus state={state} />
      <form action={action} className="flex max-w-md flex-col items-stretch gap-3">
        <FormField id="file" label="Catalogue CSV" error={state.fieldErrors?.file}>
          <Input id="file" name="file" type="file" accept=".csv,text/csv" disabled={pending} />
        </FormField>
        <FormField
          id="price_list_id"
          label="Price list for price_eur"
          error={state.fieldErrors?.price_list_id}
        >
          <select
            id="price_list_id"
            name="price_list_id"
            className={SELECT_CLASS}
            defaultValue={defaultList?.id ?? ""}
            disabled={pending}
          >
            {priceLists.length === 0 ? <option value="">No price lists yet</option> : null}
            {priceLists.map((pl) => (
              <option key={pl.id} value={pl.id}>
                {pl.name} ({pl.code}, {pl.prices_include_vat ? "incl. VAT" : "excl. VAT"})
                {pl.is_default ? " – default" : ""}
              </option>
            ))}
          </select>
        </FormField>
        <FormField
          id="exported_local"
          label="Exported from the source at (optional, your local time)"
          error={state.fieldErrors?.source_exported_at}
        >
          <Input
            id="exported_local"
            type="datetime-local"
            disabled={pending}
            onChange={(event) => setExportedAt(toIso(event.target.value))}
          />
        </FormField>
        <input type="hidden" name="source_exported_at" value={exportedAt} />
        <Button
          type="submit"
          name="intent"
          value="preview"
          variant="outline"
          disabled={pending}
          className="self-start"
        >
          {pending ? "Working…" : "Preview CSV"}
        </Button>
      </form>
      {result && counts ? (
        <section className="flex flex-col gap-3" aria-label="Import results">
          <p>
            {result.total} rows · {counts.products_created} new products · {counts.products_updated}{" "}
            updated products · {counts.variants_created} new SKUs · {counts.variants_updated}{" "}
            updated SKUs · {counts.prices_recorded} prices · {counts.stock_recorded} stock levels
            {result.already_imported ? " (already imported)" : result.dry_run ? " to import" : ""}.
          </p>
          {counts.prices_unchanged + counts.stock_unchanged > 0 ? (
            <p className="text-muted-foreground text-sm">
              Unchanged: {counts.prices_unchanged} prices, {counts.stock_unchanged} stock levels.
            </p>
          ) : null}
          {counts.prices_older_ignored + counts.stock_older_ignored > 0 ? (
            <p className="text-muted-foreground text-sm">
              Older than stored data, so not applied: {counts.prices_older_ignored} prices,{" "}
              {counts.stock_older_ignored} stock levels.
            </p>
          ) : null}
          {result.errors.length > 0 ? (
            <div>
              <h3 className="font-medium">Rows with errors (skipped)</h3>
              <ul className="list-inside list-disc text-sm">
                {result.errors.map((error, i) => (
                  <li key={i}>
                    Row {error.row}, {error.field}: {error.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.dry_run && !result.already_imported && state.csv ? (
            <form action={action}>
              <Button type="submit" name="intent" value="import" disabled={pending}>
                {pending ? "Importing…" : "Import valid rows"}
              </Button>
            </form>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
