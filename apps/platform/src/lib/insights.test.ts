import { describe, expect, it } from "vitest";

import { baselineNote, formatDuration, parseRange, percent } from "./insights";

describe("insights helpers", () => {
  it("formats durations from seconds", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(42)).toBe("42 s");
    expect(formatDuration(240)).toBe("4 min");
    expect(formatDuration(7200)).toBe("2 h");
    expect(formatDuration(7500)).toBe("2 h 5 min");
    expect(formatDuration(3 * 86400 + 4 * 3600)).toBe("3 d 4 h");
  });

  it("accepts only the offered ranges", () => {
    expect(parseRange("7")).toBe(7);
    expect(parseRange("90")).toBe(90);
    expect(parseRange("12")).toBe(30);
    expect(parseRange(undefined)).toBe(30);
  });

  it("works out shares and the baseline note", () => {
    expect(percent(1, 4)).toBe(25);
    expect(percent(1, 0)).toBeNull();
    expect(baselineNote(120)).toBe("before Onyx: about 2 h");
    expect(baselineNote(null)).toBeNull();
  });
});
