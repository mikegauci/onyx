import { describe, expect, it } from "vitest";

import { hasLinkPlaceholder, reviewSkipReason } from "./reviews";

describe("review requests", () => {
  it("explains known skip reasons and passes unknown codes through", () => {
    expect(reviewSkipReason("no_channel")).toMatch(/WhatsApp/);
    expect(reviewSkipReason("something_new")).toBe("something_new");
    expect(reviewSkipReason(null)).toBeNull();
  });

  it("needs the link placeholder in the message", () => {
    expect(hasLinkPlaceholder("Review us: {link}")).toBe(true);
    expect(hasLinkPlaceholder("Review us")).toBe(false);
  });
});
