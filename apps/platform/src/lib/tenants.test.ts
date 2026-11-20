import { describe, expect, it } from "vitest";

import {
  contrastWithWhite,
  INVITATION_STATE_LABEL,
  inviteLink,
  MIN_BRAND_CONTRAST,
  SLUG_PATTERN,
  slugify,
  usdFromMicros,
} from "./tenants";

describe("slugify", () => {
  it("turns a name into a valid slug", () => {
    expect(slugify("Ventur Auto Import")).toBe("ventur-auto-import");
    expect(slugify("  Café & Bar, Ħamrun  ")).toBe("cafe-bar-hamrun");
    expect(SLUG_PATTERN.test(slugify("Ventur Auto Import"))).toBe(true);
  });

  it("never ends in a hyphen and stays within 63 characters", () => {
    const slug = slugify(`${"a".repeat(62)} b`);
    expect(slug.length).toBeLessThanOrEqual(63);
    expect(slug.endsWith("-")).toBe(false);
  });
});

describe("brand colour contrast", () => {
  it("matches WCAG for black and white", () => {
    expect(contrastWithWhite("#000000")).toBeCloseTo(21, 0);
    expect(contrastWithWhite("#ffffff")).toBeCloseTo(1, 5);
  });

  it("accepts dark colours and refuses light ones, as the API does", () => {
    expect(contrastWithWhite("#1f4e79")!).toBeGreaterThanOrEqual(MIN_BRAND_CONTRAST);
    expect(contrastWithWhite("#ffff00")!).toBeLessThan(MIN_BRAND_CONTRAST);
    expect(contrastWithWhite("blue")).toBeNull();
  });
});

describe("labels and links", () => {
  it("covers every invitation state", () => {
    expect(Object.keys(INVITATION_STATE_LABEL)).toHaveLength(4);
  });

  it("formats AI budgets", () => {
    expect(usdFromMicros(5_000_000)).toBe("$5.00");
    expect(usdFromMicros(null)).toBe("No limit set");
  });

  it("builds the accept link", () => {
    expect(inviteLink("https://app.onyx.test", "a b")).toBe(
      "https://app.onyx.test/invitations/accept?token=a+b",
    );
  });
});
