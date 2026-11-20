import { describe, expect, it } from "vitest";

import { euros, kilometres, VEHICLE_STATUS_LABEL, vehicleSummary } from "./automotive";

describe("vehicle display", () => {
  it("formats cents exactly and says when the price is on request", () => {
    expect(euros(1_795_000)).toBe("€17,950.00");
    expect(euros(5)).toBe("€0.05");
    expect(euros(null)).toBe("Price on request");
  });

  it("summarises what is known and skips what is not", () => {
    expect(
      vehicleSummary({ year: 2019, mileage_km: 42000, fuel: "Petrol", transmission: null }),
    ).toBe("2019 · 42,000 km · Petrol");
    expect(kilometres(null)).toBe("—");
  });

  it("labels every status", () => {
    expect(Object.keys(VEHICLE_STATUS_LABEL)).toHaveLength(4);
  });
});
