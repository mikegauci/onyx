/** Browser error tracking (PR-027): on only when NEXT_PUBLIC_SENTRY_DSN is set. No replays. */
import * as Sentry from "@sentry/nextjs";

import { SENTRY_OPTIONS } from "./lib/sentry-scrub";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? "local",
    ...SENTRY_OPTIONS,
  });
  Sentry.setTag("component", "platform-browser");
}
