import { NextResponse } from "next/server";

import { newRequestId } from "@/lib/api-client";
import { MONTH_PATTERN } from "@/lib/billing";
import { platformEnv } from "@/lib/env";
import { getAccessToken } from "@/lib/supabase/server";

const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

/** The AI usage CSV from the API, as the signed-in user. The API checks the permission. */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const month = new URL(request.url).searchParams.get("month");
  if (!SLUG.test(slug) || (month !== null && !MONTH_PATTERN.test(month))) {
    return new NextResponse("Not found", { status: 404 });
  }
  const token = await getAccessToken();
  if (!token) return new NextResponse("Sign in again.", { status: 401 });
  const query = month ? `?month=${month}` : "";
  let response: Response;
  try {
    response = await fetch(`${platformEnv().apiUrl}/v1/w/${slug}/billing/usage.csv${query}`, {
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": newRequestId() },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return new NextResponse("The Onyx API is unavailable. Try again shortly.", { status: 503 });
  }
  if (!response.ok) {
    const status = [401, 403, 404].includes(response.status) ? response.status : 502;
    return new NextResponse("Usage report unavailable.", { status });
  }
  return new NextResponse(response.body, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition":
        response.headers.get("content-disposition") ?? `attachment; filename="ai-usage.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
