import { type BrowserContext, test as base, expect } from "@playwright/test";

import { E2E } from "../playwright.config";

export const USERS = {
  olivia: "olivia.owner@lumen.example.test", // Lumen owner
  mia: "mia.member@lumen.example.test", // Lumen member
  hugo: "hugo.owner@harbour.example.test", // Harbour owner
  sam: "sam.consultant@onyx.example.test", // Lumen member, Harbour admin
  pat: "pat.platform@onyx.example.test", // platform admin, no workspaces
} as const;

export const LUMEN = "/w/lumen-lighting-test";
export const HARBOUR = "/w/harbour-catering-test";

// @supabase/ssr stores the session as `sb-<first host label>-auth-token`, base64url-encoded.
const COOKIE = `sb-${new URL(E2E.authUrl).hostname.split(".")[0]}-auth-token`;

export async function signInAs(context: BrowserContext, email: string) {
  const response = await fetch(`${E2E.authUrl}/__e2e/session?email=${encodeURIComponent(email)}`);
  if (!response.ok) throw new Error(`fake auth refused ${email}`);
  const session = await response.text();
  await context.addCookies([
    {
      name: COOKIE,
      value: `base64-${Buffer.from(session).toString("base64url")}`,
      url: E2E.appUrl,
      httpOnly: false,
      sameSite: "Lax",
    },
  ]);
}

export const test = base;
export { expect };

const LUMEN_ADMIN_API = `${E2E.apiUrl}/v1/admin/organizations/lumen-lighting-test`;

/** A platform-admin call against Lumen, for test setup and cleanup. */
export async function lumenAdmin(path: string, body: unknown) {
  const session = await (
    await fetch(`${E2E.authUrl}/__e2e/session?email=${encodeURIComponent(USERS.pat)}`)
  ).json();
  const response = await fetch(`${LUMEN_ADMIN_API}${path}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`PUT ${path}: ${response.status}`);
}

export async function setLumenModule(key: string, enabled: boolean) {
  await lumenAdmin(`/modules/${key}`, { enabled });
}
