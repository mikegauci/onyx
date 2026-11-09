import { describe, expect, it } from "vitest";

import {
  duplicateOf,
  fileProblem,
  formatSize,
  knowledgePath,
  MAX_UPLOAD_BYTES,
  pageLabel,
  uploadFailureMessage,
} from "./knowledge";

describe("fileProblem", () => {
  it("accepts the formats the API reads", () => {
    for (const name of ["Care.PDF", "terms.txt", "notes.md", "guide.markdown"]) {
      expect(fileProblem(name, 10)).toBeNull();
    }
  });

  it("refuses Word files, empty files and files over the upload limit", () => {
    expect(fileProblem("guide.docx", 10)).toMatch(/Word files/);
    expect(fileProblem("guide.pdf", 0)).toBe("Choose a file.");
    expect(fileProblem("guide.pdf", MAX_UPLOAD_BYTES + 1)).toMatch(/4 MB/);
    expect(fileProblem("guide.pdf", MAX_UPLOAD_BYTES)).toBeNull();
  });
});

describe("display helpers", () => {
  it("formats sizes and pages", () => {
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(2048)).toBe("2 KB");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(pageLabel(4)).toBe("Page 4");
    expect(pageLabel(null)).toBeNull();
  });

  it("encodes the workspace slug in paths", () => {
    expect(knowledgePath("a b", "documents", "x")).toBe("/w/a%20b/m/knowledge/documents/x");
  });
});

describe("upload failures", () => {
  const failure = (status: number, details: unknown[] = []) =>
    ({
      ok: false,
      status,
      requestId: "r",
      error: { code: "conflict", message: "m", details, request_id: "r" },
    }) as never;

  it("finds the existing document of a duplicate", () => {
    const ref = "8c6f0b0e-0000-4000-8000-000000000000";
    expect(duplicateOf(failure(409, [{ loc: ["body"], msg: "m", type: "duplicate", ref }]))).toBe(
      ref,
    );
    expect(duplicateOf(failure(422))).toBeNull();
  });

  it("explains an AI outage and a used-up budget", () => {
    expect(uploadFailureMessage(503)).toMatch(/AI is unavailable/);
    expect(uploadFailureMessage(429)).toMatch(/budget/);
    expect(uploadFailureMessage(422)).toBeNull();
  });
});
