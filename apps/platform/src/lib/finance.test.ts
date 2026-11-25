import { describe, expect, it } from "vitest";

import { bpFrom, percent, termLabel } from "./finance";

describe("finance helpers", () => {
  it("shows rates and terms", () => {
    expect(percent(650)).toBe("6.5%");
    expect(percent(400)).toBe("4%");
    expect(termLabel(60)).toBe("5 years");
    expect(termLabel(42)).toBe("3½ years");
    expect(termLabel(6)).toBe("6 months");
  });

  it("reads typed percentages as basis points", () => {
    expect(bpFrom("6.5")).toBe(650);
    expect(bpFrom("4 %")).toBe(400);
    expect(bpFrom("")).toBeNull();
    expect(bpFrom("6.555")).toBe("invalid");
  });
});
