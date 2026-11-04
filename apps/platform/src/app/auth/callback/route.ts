import { type NextRequest, NextResponse } from "next/server";

import { platformEnv } from "@/lib/env";
import { safeRedirect } from "@/lib/safe-redirect";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/** Completes a magic-link sign-in (PKCE code exchange), then returns to a same-origin path. */
export async function GET(request: NextRequest) {
  const { appUrl } = platformEnv();
  const code = request.nextUrl.searchParams.get("code");
  const next = safeRedirect(request.nextUrl.searchParams.get("next"), appUrl, "/workspaces");
  const supabase = await createSupabaseServerClient();

  if (!code || !supabase) {
    return NextResponse.redirect(new URL("/login?error=link", appUrl));
  }
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(new URL("/login?error=link", appUrl));
  }
  return NextResponse.redirect(new URL(next, appUrl));
}
