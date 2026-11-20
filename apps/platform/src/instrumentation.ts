/**
 * Server-side error tracking (PR-027): on only when SENTRY_DSN is set. Request errors in
 * server components, route handlers and server actions are captured with the scrubbing in
 * `lib/sentry-scrub`. No source maps are uploaded (that needs a Sentry auth token).
 */
import type { Instrumentation } from "next";

import { SENTRY_OPTIONS } from "./lib/sentry-scrub";

export async function register() {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.init({
    dsn,
    environment: process.env.VERCEL_ENV ?? "local",
    release: process.env.VERCEL_GIT_COMMIT_SHA,
    ...SENTRY_OPTIONS,
  });
  Sentry.setTag("component", "platform");
}

export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (!process.env.SENTRY_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
};
