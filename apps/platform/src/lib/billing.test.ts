import { describe, expect, it } from "vitest";

import { billingStatus, recentMonths, usd } from "./billing";

describe("usd", () => {
  it("formats micros exactly", () => {
    expect(usd(50_000_000)).toBe("$50.00");
    expect(usd(4_200, 6)).toBe("$0.004200");
    expect(usd(1_999_999)).toBe("$1.99"); // truncates, never rounds a charge up
    expect(usd(0)).toBe("$0.00");
  });
});

describe("billing status", () => {
  it("labels known statuses and the absence of a plan", () => {
    expect(billingStatus("past_due")).toEqual({ label: "Payment overdue", variant: "warning" });
    expect(billingStatus(null).label).toBe("No plan");
    expect(billingStatus("something_new").label).toBe("something_new");
  });
});

describe("recentMonths", () => {
  it("goes back across a year boundary", () => {
    expect(recentMonths(new Date("2026-02-15T00:00:00Z"), 3)).toEqual([
      "2026-02",
      "2026-01",
      "2025-12",
    ]);
  });
});
