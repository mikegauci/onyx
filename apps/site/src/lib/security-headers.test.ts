import { securityHeaders } from "./security-headers";

const keys = (env: string | undefined) => securityHeaders(env).map((h) => h.key);

describe("securityHeaders", () => {
  it.each([undefined, "development", "preview", "production"])(
    "always sets baseline headers (%s)",
    (env) => {
      expect(keys(env)).toEqual(
        expect.arrayContaining([
          "X-Content-Type-Options",
          "X-Frame-Options",
          "Referrer-Policy",
          "Permissions-Policy",
        ]),
      );
    },
  );

  it("marks non-production builds noindex and omits HSTS", () => {
    expect(keys("preview")).toContain("X-Robots-Tag");
    expect(keys("preview")).not.toContain("Strict-Transport-Security");
    expect(keys(undefined)).toContain("X-Robots-Tag");
  });

  it("sends HSTS and allows indexing headers only in production", () => {
    expect(keys("production")).toContain("Strict-Transport-Security");
    expect(keys("production")).not.toContain("X-Robots-Tag");
  });
});
