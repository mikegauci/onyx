"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { type CatalogueImportResult, cataloguePath } from "@/lib/catalogue";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

const MAX_FILE_BYTES = 2_000_000;

function done(slug: string, message: string): FormState {
  revalidatePath(cataloguePath(slug), "layout");
  return { status: "ok", message };
}

// --- archiving -------------------------------------------------------------------------------

export async function setProductArchived(
  slug: string,
  productId: string,
  archived: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/catalogue/products/{product_id}/archive", {
      params: { path: { slug, product_id: productId } },
      body: { archived },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, archived ? "Product archived." : "Product restored.");
}

export async function setVariantArchived(
  slug: string,
  variantId: string,
  archived: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/catalogue/variants/{variant_id}/archive", {
      params: { path: { slug, variant_id: variantId } },
      body: { archived },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, archived ? "SKU archived." : "SKU restored.");
}

// --- VAT rates and price lists ---------------------------------------------------------------

export async function createVatRate(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/catalogue/vat-rates", {
      params: { path: { slug } },
      body: {
        code: text(formData, "code"),
        name: text(formData, "name"),
        rate_percent: text(formData, "rate_percent"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, `VAT rate ${outcome.data.code} created.`);
}

export async function setVatRateArchived(
  slug: string,
  vatRateId: string,
  archived: boolean,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/catalogue/vat-rates/{vat_rate_id}/archive", {
      params: { path: { slug, vat_rate_id: vatRateId } },
      body: { archived },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, archived ? "VAT rate archived." : "VAT rate restored.");
}

export async function createPriceList(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/catalogue/price-lists", {
      params: { path: { slug } },
      body: {
        code: text(formData, "code"),
        name: text(formData, "name"),
        prices_include_vat: text(formData, "prices_include_vat") === "true",
        is_default: formData.get("is_default") === "true",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, `Price list ${outcome.data.code} created.`);
}

export async function makeDefaultPriceList(
  slug: string,
  priceListId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/catalogue/price-lists/{price_list_id}", {
      params: { path: { slug, price_list_id: priceListId } },
      body: { is_default: true },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, `${outcome.data.code} is now the default price list.`);
}

// --- import ----------------------------------------------------------------------------------

export type CatalogueImportState = FormState & {
  result?: CatalogueImportResult;
  csv?: string;
  fileName?: string;
  priceListId?: string | null;
  exportedAt?: string | null;
};

/**
 * Step 1 (`intent=preview`): read the chosen file and ask the API for a dry run.
 * Step 2 (`intent=import`): send the same text and options again with `dry_run: false`.
 */
export async function importCatalogue(
  slug: string,
  prev: CatalogueImportState,
  formData: FormData,
): Promise<CatalogueImportState> {
  const intent = text(formData, "intent");
  let csv: string;
  let fileName: string | undefined;
  let priceListId: string | null;
  let exportedAt: string | null;
  if (intent === "import") {
    csv = prev.csv ?? "";
    fileName = prev.fileName;
    priceListId = prev.priceListId ?? null;
    exportedAt = prev.exportedAt ?? null;
  } else {
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) {
      return { status: "error", message: "Choose a CSV file.", fieldErrors: { file: "Required." } };
    }
    if (file.size > MAX_FILE_BYTES) {
      return {
        status: "error",
        message: "The file is larger than 2 MB.",
        fieldErrors: { file: "Too large." },
      };
    }
    csv = await file.text();
    fileName = file.name.slice(0, 255);
    priceListId = optionalText(formData, "price_list_id");
    exportedAt = optionalText(formData, "source_exported_at");
  }
  const dryRun = intent !== "import";
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/catalogue/import", {
      params: { path: { slug } },
      body: {
        csv,
        filename: fileName ?? null,
        price_list_id: priceListId,
        source_exported_at: exportedAt,
        dry_run: dryRun,
      },
    }),
  );
  if (!outcome.ok) {
    const failure = failureState(outcome);
    return {
      ...failure,
      fieldErrors: failure.fieldErrors?.csv
        ? { ...failure.fieldErrors, file: failure.fieldErrors.csv }
        : failure.fieldErrors,
    };
  }
  const result = outcome.data;
  if (result.already_imported) {
    return {
      status: "ok",
      message: "This file was already imported into this price list. Nothing changed.",
      result,
    };
  }
  if (dryRun) {
    return {
      status: "ok",
      message: `Preview of ${fileName ?? "the file"}: nothing has been saved yet.`,
      result,
      csv,
      fileName,
      priceListId,
      exportedAt,
    };
  }
  revalidatePath(cataloguePath(slug), "layout");
  return {
    status: "ok",
    message: `Imported ${result.counts.variants_created} new and ${result.counts.variants_updated} updated SKUs, ${result.counts.prices_recorded} prices and ${result.counts.stock_recorded} stock levels.`,
    result,
  };
}
