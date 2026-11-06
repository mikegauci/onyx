import { runBlockedReason, topicLabel, usdFromMicros } from "./assistant";
import { messageHeading, type Message } from "./inbox";

describe("usdFromMicros", () => {
  it.each([
    [0, "$0.0000"],
    [4_200, "$0.0042"],
    [1_234_567, "$1.2345"],
    [5_000_000, "$5.0000"],
    [99, "$0.0000"],
  ])("formats %i micros as %s", (micros, expected) => {
    expect(usdFromMicros(micros)).toBe(expected);
  });
});

describe("topicLabel", () => {
  it("turns a slug into words", () => {
    expect(topicLabel("lead_times")).toBe("Lead times");
  });
});

describe("runBlockedReason", () => {
  it("blocks closed conversations only", () => {
    expect(runBlockedReason("closed")).toMatch(/Reopen/);
    expect(runBlockedReason("open")).toBeNull();
    expect(runBlockedReason("waiting_on_customer")).toBeNull();
  });
});

describe("messageHeading", () => {
  const note = { direction: "note", author: null } as unknown as Message;

  it("labels notes written by the assistant", () => {
    expect(messageHeading({ ...note, author_kind: "assistant" })).toBe(
      "Internal note by Assistant",
    );
  });

  it("keeps the former-member label for staff notes without an author", () => {
    expect(messageHeading({ ...note, author_kind: "staff" })).toBe(
      "Internal note by a former member",
    );
  });
});
