import { describe, expect, it } from "vitest";

import { composeKinds, DELIVERY_LABEL, deliveryBlocksAddress } from "./inbox";

describe("composeKinds", () => {
  it("never offers to log a reply on email", () => {
    expect(composeKinds("email")).toEqual(["customer", "note"]);
  });

  it("keeps logging replies on manual channels", () => {
    expect(composeKinds("manual")).toContain("reply");
  });
});

describe("delivery status", () => {
  it("has a label for every status", () => {
    expect(Object.keys(DELIVERY_LABEL)).toHaveLength(7);
  });

  it("warns that bounces, complaints and suppressions block the address", () => {
    expect(deliveryBlocksAddress("bounced")).toBe(true);
    expect(deliveryBlocksAddress("complained")).toBe(true);
    expect(deliveryBlocksAddress("suppressed")).toBe(true);
    expect(deliveryBlocksAddress("delivered")).toBe(false);
    expect(deliveryBlocksAddress("delayed")).toBe(false);
  });
});
