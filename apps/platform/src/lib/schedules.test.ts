import { describe, expect, it } from "vitest";

import { paidPercent } from "./schedules";

describe("schedules", () => {
  it("shows the share paid, capped at 100", () => {
    expect(paidPercent({ paid_cents: 150_000, total_cents: 300_000 })).toBe(50);
    expect(paidPercent({ paid_cents: 400, total_cents: 300 })).toBe(100);
    expect(paidPercent({ paid_cents: 0, total_cents: 0 })).toBe(0);
  });
});
