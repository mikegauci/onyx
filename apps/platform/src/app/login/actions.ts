"use server";

import { redirect } from "next/navigation";

import { platformEnv } from "@/lib/env";
import { safeRedirect } from "@/lib/safe-redirect";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Sends a magic link. The response never reveals whether the email has an account. */
export async function sendMagicLink(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim();
  const { appUrl } = platformEnv();
  const next = safeRedirect(String(formData.get("next") ?? ""), appUrl, "/workspaces");
  if (!EMAIL.test(email)) redirect(`/login?error=email&next=${encodeURIComponent(next)}`);

  const supabase = await createSupabaseServerClient();
  if (!supabase) redirect("/login?error=unconfigured");

  const callback = new URL("/auth/callback", appUrl);
  callback.searchParams.set("next", next);
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: callback.toString(), shouldCreateUser: true },
  });
  redirect(error ? "/login?error=send" : "/login?sent=1");
}
