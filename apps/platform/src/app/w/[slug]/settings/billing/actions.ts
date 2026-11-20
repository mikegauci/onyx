"use server";

import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { platformEnv } from "@/lib/env";
import { type FormState, failureState } from "@/lib/form-state";

function returnUrl(slug: string): string {
  return new URL(
    `/w/${encodeURIComponent(slug)}/settings/billing`,
    platformEnv().appUrl,
  ).toString();
}

/** Opens Stripe Checkout for a plan. Owners only; the API decides. */
export async function startCheckout(
  slug: string,
  plan: "starter" | "growth",
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/billing/checkout", {
      params: { path: { slug } },
      body: { plan, return_url: returnUrl(slug) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  redirect(outcome.data.url);
}

/** Opens the Stripe billing portal: payment details, invoices, plan changes, cancelling. */
export async function openPortal(slug: string, _prev: FormState): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/billing/portal", {
      params: { path: { slug } },
      body: { return_url: returnUrl(slug) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  redirect(outcome.data.url);
}
