import { safeRedirect } from "./safe-redirect";

const APP = "https://app.example.test";

describe("safeRedirect", () => {
  it.each([
    ["/w/onyx-studio", "/w/onyx-studio"],
    ["/dashboard?tab=1#x", "/dashboard?tab=1#x"],
  ])("keeps same-origin path %s", (input, expected) => {
    expect(safeRedirect(input, APP)).toBe(expected);
  });

  it.each([
    null,
    undefined,
    "",
    "https://evil.example/",
    "//evil.example/path",
    "/\\evil.example",
    "javascript:alert(1)",
    "dashboard",
  ])("falls back for %s", (input) => {
    expect(safeRedirect(input, APP)).toBe("/dashboard");
  });
});
