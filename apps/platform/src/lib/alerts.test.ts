import { describe, expect, it } from "vitest";

import { centsFromEuros, skipReason, wantedSummary } from "./alerts";

describe("alerts", () => {
  it("summarises what a buyer wants", () => {
    expect(
      wantedSummary({
        make: "Volkswagen",
        model: "Golf",
        price_max_cents: 1_800_000,
        year_min: 2018,
        mileage_max_km: 60_000,
        fuel: null,
      }),
    ).toBe("Volkswagen Golf · up to €18,000 · from 2018 · under 60,000 km");
  });

  it("reads euros exactly, without floats", () => {
    expect(centsFromEuros("18,000")).toBe(1_800_000);
    expect(centsFromEuros("€17950.5")).toBe(1_795_050);
    expect(centsFromEuros("0.29")).toBe(29);
    expect(centsFromEuros("")).toBeNull();
    expect(centsFromEuros("abc")).toBeNull();
  });

  it("explains skip reasons and keeps unknown codes", () => {
    expect(skipReason("no_consent")).toContain("not agreed");
    expect(skipReason("new_code")).toBe("new_code");
    expect(skipReason(null)).toBeNull();
  });
});
