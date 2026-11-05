import { isProtectedPath, loginRedirect } from "./auth-paths";

describe("isProtectedPath", () => {
  it.each([
    "/workspaces",
    "/w/lumen",
    "/w/lumen/settings",
    "/w",
    "/admin",
    "/admin/status",
    "/invitations/accept",
  ])("protects %s", (path) => {
    expect(isProtectedPath(path)).toBe(true);
  });

  it.each([
    "/",
    "/login",
    "/auth/callback",
    "/dashboard",
    "/workspaces-public",
    "/wiki",
    "/administrator",
  ])("leaves %s public", (path) => {
    expect(isProtectedPath(path)).toBe(false);
  });
});

describe("loginRedirect", () => {
  it("keeps the path and query as next", () => {
    const url = loginRedirect("/w/lumen", "?tab=a", "https://app.example.test/x");
    expect(url.origin).toBe("https://app.example.test");
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("next")).toBe("/w/lumen?tab=a");
  });
});
