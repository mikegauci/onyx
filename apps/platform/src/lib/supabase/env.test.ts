import { supabaseEnv } from "./env";

const KEY = "sb_publishable_abc123";

describe("supabaseEnv", () => {
  it("disables sign-in locally when unset", () => {
    expect(supabaseEnv({ NODE_ENV: "test" })).toBeNull();
  });

  it("returns the URL and publishable key", () => {
    expect(
      supabaseEnv({
        NODE_ENV: "test",
        NEXT_PUBLIC_SUPABASE_URL: "https://ref.supabase.co/",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: KEY,
      }),
    ).toEqual({ url: "https://ref.supabase.co", publishableKey: KEY });
  });

  it("fails a deployed build without Supabase settings", () => {
    expect(() => supabaseEnv({ NODE_ENV: "production", VERCEL_ENV: "preview" })).toThrow(
      "NEXT_PUBLIC_SUPABASE_URL",
    );
  });

  it("rejects half-configured settings", () => {
    expect(() =>
      supabaseEnv({ NODE_ENV: "test", NEXT_PUBLIC_SUPABASE_URL: "https://ref.supabase.co" }),
    ).toThrow("must both be set");
  });

  it("rejects a secret key in a public variable", () => {
    expect(() =>
      supabaseEnv({
        NODE_ENV: "test",
        NEXT_PUBLIC_SUPABASE_URL: "https://ref.supabase.co",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_secret_xyz",
      }),
    ).toThrow("must not be a secret key");
  });

  it("requires https in deployed builds", () => {
    expect(() =>
      supabaseEnv({
        NODE_ENV: "production",
        VERCEL_ENV: "preview",
        NEXT_PUBLIC_SUPABASE_URL: "http://ref.supabase.co",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: KEY,
      }),
    ).toThrow();
  });
});
