import { NextResponse } from "next/server";

import { newRequestId } from "@/lib/api-client";
import { platformEnv } from "@/lib/env";
import { getAccessToken } from "@/lib/supabase/server";

const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

/** Downloads a blank finance form (KYC & Loan Request, or CCR) as the signed-in user. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string; kind: string }> },
) {
  const { slug, kind } = await params;
  if (!SLUG.test(slug) || !["kyc", "ccr"].includes(kind)) {
    return new NextResponse("Not found", { status: 404 });
  }
  const token = await getAccessToken();
  if (!token) return new NextResponse("Sign in again.", { status: 401 });
  let response: Response;
  try {
    response = await fetch(`${platformEnv().apiUrl}/v1/w/${slug}/deals/finance/forms/${kind}`, {
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": newRequestId() },
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    return new NextResponse("The Onyx API is unavailable. Try again shortly.", { status: 503 });
  }
  if (!response.ok) {
    const status = [401, 403, 404].includes(response.status) ? response.status : 502;
    return new NextResponse(
      status === 404 ? "This form has not been uploaded yet." : "Unavailable.",
      {
        status,
      },
    );
  }
  return new NextResponse(response.body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition":
        response.headers.get("content-disposition") ?? `attachment; filename="${kind}.pdf"`,
      "Cache-Control": "private, no-store",
    },
  });
}
