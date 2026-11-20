import { describe, expect, it } from "vitest";

import { taskHref, tasksLabel } from "./tasks";

describe("tasks", () => {
  it("links a reply task to its draft", () => {
    expect(taskHref("lumen", { subject_type: "outbound_draft", subject_id: "d1" })).toBe(
      "/w/lumen/m/outbound/drafts/d1",
    );
    expect(taskHref("lumen", { subject_type: "other", subject_id: "x" })).toBeNull();
  });

  it("shows the open count", () => {
    expect(tasksLabel(0)).toBe("Tasks");
    expect(tasksLabel(3)).toBe("Tasks (3)");
  });
});
