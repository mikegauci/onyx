/** Display helpers for the catalogue. Prices, VAT and stock rules come from the API. */
import type { components } from "@onyx/api-client";

export type ProductSummary = components["schemas"]["ProductSummary"];
export type ProductDetail = components["schemas"]["ProductDetail"];
export type Variant = components["schemas"]["VariantOut"];
export type Price = components["schemas"]["PriceOut"];
export type PriceList = components["schemas"]["PriceListOut"];
export type VatRate = components["schemas"]["VatRateOut"];
export type ImportRun = components["schemas"]["ImportRunOut"];
export type CatalogueImportResult = components["schemas"]["CatalogueImportResult"];
export type Availability = Variant["availability"];

export function cataloguePath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/catalogue`, ...parts].join("/");
}

/** The API's exact decimal string with the euro sign; no arithmetic happens here. */
export function formatEuro(amount: string): string {
  return `€${amount}`;
}

export const AVAILABILITY_LABEL: Record<Availability, string> = {
  in_stock: "In stock",
  out_of_stock: "Out of stock",
  unknown: "Stock unknown",
};

export const AVAILABILITY_VARIANT: Record<Availability, "success" | "warning" | "outline"> = {
  in_stock: "success",
  out_of_stock: "warning",
  unknown: "outline",
};

/** "From catalogue.csv (exported …)", or "Entered directly" when no import is recorded. */
export function describeSource(source: Price["source"], format: (iso: string) => string): string {
  if (!source.import_run_id) return "Entered directly";
  const file = source.filename ? `From ${source.filename}` : "From a CSV import";
  return source.source_exported_at
    ? `${file} (exported ${format(source.source_exported_at)})`
    : file;
}

export function attributeLabel(name: string): string {
  return name.replaceAll("_", " ");
}
