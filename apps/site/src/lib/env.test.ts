import { siteEnv } from "./env";

describe("siteEnv", () => {
  it("uses local defaults outside deployed builds", () => {
    expect(siteEnv({} as unknown as NodeJS.ProcessEnv)).toEqual({
      platformUrl: "http://localhost:3001",
      siteUrl: "http://localhost:3000",
      indexable: false,
    });
  });

  it("falls back to the Vercel production domain for the site URL", () => {
    const env = siteEnv({
      VERCEL_ENV: "preview",
      NEXT_PUBLIC_PLATFORM_URL: "https://app.example.test",
      VERCEL_PROJECT_PRODUCTION_URL: "onyx.example.test",
    } as unknown as NodeJS.ProcessEnv);
    expect(env.siteUrl).toBe("https://onyx.example.test");
    expect(env.indexable).toBe(false);
  });

  it("is indexable only in production", () => {
    const env = siteEnv({
      VERCEL_ENV: "production",
      NEXT_PUBLIC_PLATFORM_URL: "https://app.onyx.mt",
      NEXT_PUBLIC_SITE_URL: "https://onyx.mt",
    } as unknown as NodeJS.ProcessEnv);
    expect(env).toEqual({
      platformUrl: "https://app.onyx.mt",
      siteUrl: "https://onyx.mt",
      indexable: true,
    });
  });
});
