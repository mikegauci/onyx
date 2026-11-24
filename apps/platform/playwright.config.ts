import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke navigation tests against the real API and a local Postgres (`make up`).
 * Sign-in uses e2e/fake-auth.mjs, a local JWKS the API and dashboard verify like Supabase's.
 */
export const E2E = {
  appUrl: "http://localhost:3101",
  apiUrl: "http://127.0.0.1:8100",
  authUrl: "http://127.0.0.1:54399",
  databaseUrl:
    process.env.E2E_DATABASE_URL ??
    "postgresql+psycopg://onyx:onyx_local_only@127.0.0.1:54322/onyx_e2e",
};

/** Signs the e2e Stripe webhooks. A test value for the fake billing provider only. */
export const STRIPE_E2E_SECRET = "whsec_e2e_billing_secret";
export const STRIPE_E2E_PRICES = { starter: "price_e2estarter", growth: "price_e2egrowth" };

/** Signs the e2e telephony (missed-call) webhooks. A test value for the fake provider only. */
export const TELEPHONY_E2E_SECRET = "telephony-e2e-secret";

/** Signs the e2e WhatsApp webhooks. A test value for the fake provider only. */
export const WHATSAPP_E2E_SECRET = "whatsapp-e2e-app-secret";

const reuse = !process.env.CI;
// Bundled Chromium needs macOS 14+. On older Macs set E2E_BROWSER_CHANNEL=chrome to drive the
// installed Google Chrome (a fresh, isolated profile; never your own).
const channel = process.env.E2E_BROWSER_CHANNEL || undefined;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: E2E.appUrl,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], channel },
      testIgnore: /mobile\.spec/,
    },
    { name: "mobile", use: { ...devices["Pixel 7"], channel }, testMatch: /mobile\.spec/ },
  ],
  webServer: [
    {
      command: "node e2e/fake-auth.mjs",
      url: `${E2E.authUrl}/health`,
      reuseExistingServer: reuse,
    },
    {
      command: "uv run uvicorn app.main:app --host 127.0.0.1 --port 8100",
      cwd: "../api",
      url: `${E2E.apiUrl}/health`,
      // API logs (JSON, with tracebacks for unhandled errors) appear in the CI output.
      stdout: "pipe",
      reuseExistingServer: reuse,
      env: {
        ONYX_API_ENVIRONMENT: "test",
        ONYX_API_DATABASE_URL: E2E.databaseUrl,
        ONYX_API_SUPABASE_URL: E2E.authUrl,
        ONYX_API_CORS_ORIGINS: E2E.appUrl,
        // Email channels connected to the in-memory fake provider: nothing is sent anywhere.
        ONYX_API_EMAIL_PROVIDER: "fake",
        ONYX_API_RESEND_API_KEY: "re_e2e_unused",
        ONYX_API_RESEND_WEBHOOK_SECRET: "whsec_ZTJlLXVudXNlZC1zZWNyZXQ=",
        ONYX_API_EMAIL_INBOUND_DOMAIN: "in.onyx.test",
        ONYX_API_EMAIL_FROM_DOMAIN: "reply.onyx.test",
        // WhatsApp channels on the in-memory fake provider. Tests sign webhooks with this
        // secret (e2e/whatsapp.spec.ts); nothing reaches Meta.
        ONYX_API_WHATSAPP_PROVIDER: "fake",
        ONYX_API_WHATSAPP_APP_SECRET: WHATSAPP_E2E_SECRET,
        ONYX_API_WHATSAPP_VERIFY_TOKEN: "e2e-verify-token",
        ONYX_API_WHATSAPP_ACCESS_TOKEN: "e2e-unused-token",
        // Missed calls arrive as locally signed test webhooks; no telephony provider is called.
        ONYX_API_TELEPHONY_PROVIDER: "fake",
        ONYX_API_TELEPHONY_WEBHOOK_URL: `${E2E.apiUrl}/v1/webhooks/telephony`,
        ONYX_API_TELEPHONY_FAKE_SECRET: TELEPHONY_E2E_SECRET,
        // Vehicle imports read a built-in demo site; nothing is fetched from the internet.
        ONYX_API_AUTOMOTIVE_SITE: "fake",
        // Billing on the in-memory fake provider: checkout links point back to the dashboard.
        ONYX_API_BILLING_PROVIDER: "fake",
        ONYX_API_STRIPE_API_KEY: "sk_test_e2e_unused",
        ONYX_API_STRIPE_WEBHOOK_SECRET: STRIPE_E2E_SECRET,
        ONYX_API_STRIPE_PRICE_STARTER: STRIPE_E2E_PRICES.starter,
        ONYX_API_STRIPE_PRICE_GROWTH: STRIPE_E2E_PRICES.growth,
      },
    },
    {
      command: "pnpm exec next dev --port 3101",
      url: `${E2E.appUrl}/login`,
      reuseExistingServer: reuse,
      timeout: 180_000,
      env: {
        NEXT_DIST_DIR: ".next-e2e",
        NEXT_PUBLIC_API_URL: E2E.apiUrl,
        NEXT_PUBLIC_APP_URL: E2E.appUrl,
        NEXT_PUBLIC_SITE_URL: "http://localhost:3000",
        NEXT_PUBLIC_SUPABASE_URL: E2E.authUrl,
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_e2e_fake",
      },
    },
  ],
});
