import { NextResponse } from "next/server";

import { platformEnv } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function POST() {
  const supabase = await createSupabaseServerClient();
  await supabase?.auth.signOut();
  return NextResponse.redirect(new URL("/login", platformEnv().appUrl), { status: 303 });
}
