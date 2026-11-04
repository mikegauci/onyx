import { InvalidEnvError, publicUrl } from "./public-url";

const LOCAL = "http://localhost:3001";

describe("publicUrl", () => {
  it("falls back to the local default outside deployed builds", () => {
    expect(publicUrl("X", undefined, LOCAL, undefined)).toBe(LOCAL);
    expect(publicUrl("X", "", LOCAL, "development")).toBe(LOCAL);
  });

  it("normalises to an origin", () => {
    expect(publicUrl("X", "https://app.example.test/", LOCAL, "preview")).toBe(
      "https://app.example.test",
    );
  });

  it.each(["preview", "production"])("requires a value in %s builds", (env) => {
    expect(() => publicUrl("X", undefined, LOCAL, env)).toThrow(InvalidEnvError);
  });

  it.each([
    "http://app.example.test",
    "https://localhost:3001",
    "https://127.0.0.1",
    "https://dev.localhost",
    "https://app.example.test/path",
    "https://user:pw@app.example.test",
    "not a url",
  ])("rejects %s in deployed builds", (value) => {
    expect(() => publicUrl("X", value, LOCAL, "preview")).toThrow(InvalidEnvError);
  });
});
