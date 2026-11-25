import { describe, expect, it } from "vitest";

import { centsFrom, nextStages } from "./deals";

describe("deal helpers", () => {
  it("reads euro amounts exactly", () => {
    expect(centsFrom("16,500")).toBe(1_650_000);
    expect(centsFrom("€499.5")).toBe(49_950);
    expect(centsFrom("")).toBeNull();
    expect(centsFrom("12.345")).toBe("invalid");
    expect(centsFrom("abc")).toBe("invalid");
  });

  it("offers only the moves the rules allow", () => {
    expect(nextStages({ stage: "reserved", financed: false })).toEqual([
      "deposit_received",
      "documents",
      "sold",
      "cancelled",
    ]);
    expect(nextStages({ stage: "documents", financed: true })).toContain("finance");
    expect(nextStages({ stage: "sold", financed: false })).toEqual(["collected"]);
    expect(nextStages({ stage: "cancelled", financed: false })).toEqual([]);
  });
});
