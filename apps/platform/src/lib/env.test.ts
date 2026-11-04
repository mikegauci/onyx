import { platformEnv } from "./env";

const preview = {
  NODE_ENV: "production",
  VERCEL_ENV: "preview",
  NEXT_PUBLIC_API_URL: "https://api-preview.example.test",
  NEXT_PUBLIC_SITE_URL: "https://site-preview.example.test",
} as const;

describe("platformEnv", () => {
  it("uses local defaults outside deployed builds", () => {
    expect(platformEnv({ NODE_ENV: "test" })).toEqual({
      apiUrl: "http://localhost:8000",
      siteUrl: "http://localhost:3000",
      appUrl: "http://localhost:3001",
    });
  });

  it("defaults the app URL to the Vercel branch URL in previews", () => {
    expect(platformEnv({ ...preview, VERCEL_BRANCH_URL: "platform-git-x.vercel.app" }).appUrl).toBe(
      "https://platform-git-x.vercel.app",
    );
  });

  it("fails a preview build without an app URL", () => {
    expect(() => platformEnv(preview)).toThrow("NEXT_PUBLIC_APP_URL");
  });
});
