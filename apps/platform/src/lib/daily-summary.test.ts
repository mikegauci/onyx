import { describe, expect, it } from "vitest";

import { e164, reasonText, statusLabel, timeValue } from "./daily-summary";

describe("daily summary", () => {
  it("normalises WhatsApp numbers to E.164", () => {
    expect(e164("+356 7900 0001")).toBe("+35679000001");
    expect(e164("0035679000001")).toBe("+35679000001");
    expect(e164("79000001")).toBeNull();
    expect(e164("")).toBeNull();
  });

  it("shows times as hours and minutes", () => {
    expect(timeValue("19:00:00")).toBe("19:00");
  });

  it("explains results", () => {
    expect(reasonText("no_template")).toMatch(/template/);
    expect(reasonText("email_rate_limited")).toMatch(/email provider/);
    expect(reasonText(null)).toBeNull();
    expect(statusLabel("partly_sent")).toBe("Partly sent");
  });
});
