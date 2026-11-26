import { describe, expect, it } from "vitest";

import { daysUntil, formatDay, reminderSkipReason } from "./reminders";

describe("reminders", () => {
  it("formats dates the Maltese way", () => {
    expect(formatDay("2027-03-01")).toBe("01/03/2027");
    expect(formatDay(null)).toBe("—");
  });

  it("counts days to a due date", () => {
    const today = new Date(Date.UTC(2027, 1, 27));
    expect(daysUntil("2027-03-01", today)).toBe(2);
    expect(daysUntil("2027-02-20", today)).toBe(-7);
  });

  it("explains skip reasons", () => {
    expect(reminderSkipReason("paused")).toMatch(/paused/);
    expect(reminderSkipReason("other")).toBe("other");
  });
});
