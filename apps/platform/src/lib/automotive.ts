/** Display helpers for vehicles. Stock, prices and statuses come from the API. */
import type { components } from "@onyx/api-client";

export type Vehicle = components["schemas"]["VehicleOut"];
export type VehicleStatus = components["schemas"]["VehicleStatus"];
export type ImportPreview = components["schemas"]["ImportPreview"];

export function automotivePath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/automotive`, ...parts].join("/");
}

export const VEHICLE_STATUS_LABEL: Record<VehicleStatus, string> = {
  available: "Available",
  reserved: "Reserved",
  sold: "Sold",
  withdrawn: "No longer listed",
};

export const VEHICLE_STATUS_VARIANT: Record<
  VehicleStatus,
  "success" | "warning" | "outline" | "secondary"
> = {
  available: "success",
  reserved: "warning",
  sold: "secondary",
  withdrawn: "outline",
};

/** Cents as euros, exactly: 1795000 → "€17,950.00". Null means price on request. */
export function euros(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "Price on request";
  const whole = Math.floor(Math.abs(cents) / 100);
  const part = String(Math.abs(cents) % 100).padStart(2, "0");
  return `${cents < 0 ? "-" : ""}€${whole.toLocaleString("en-GB")}.${part}`;
}

export function kilometres(km: number | null | undefined): string {
  return km === null || km === undefined ? "—" : `${km.toLocaleString("en-GB")} km`;
}

/** A short line for a vehicle: "2019 · 42,000 km · Petrol · Automatic". */
export function vehicleSummary(v: Pick<Vehicle, "year" | "mileage_km" | "fuel" | "transmission">) {
  return [v.year, v.mileage_km !== null ? kilometres(v.mileage_km) : null, v.fuel, v.transmission]
    .filter((part) => part !== null && part !== undefined && part !== "")
    .join(" · ");
}

/** Why the site could not be read, for staff. Codes come from the API. */
export const SOURCE_ERROR_TEXT: Record<string, string> = {
  must_be_https: "Use the site's https address, such as https://example.com.",
  port_not_allowed: "Use the site's normal https address, without a port.",
  host_not_found: "That address could not be found.",
  host_not_public: "That address is not a public website.",
  not_a_vehica_site: "That site does not offer Vehica car listings.",
  redirect_not_followed: "The site redirected elsewhere. Use its final address.",
  timeout: "The site took too long to answer. Try again.",
  unreachable: "The site could not be reached. Try again.",
  response_too_large: "The site's answer was too large to import.",
  not_json: "The site did not answer with listings.",
};
