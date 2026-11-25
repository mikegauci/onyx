import { NextResponse } from "next/server";

import { newRequestId } from "@/lib/api-client";
import { platformEnv } from "@/lib/env";
import { getAccessToken } from "@/lib/supabase/server";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

/** Downloads everything Onyx holds about a contact (owners only; the API checks and audits). */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string; id: string }> },
) {
  const { slug, id } = await params;
  if (!SLUG.test(slug) || !UUID.test(id)) return new NextResponse("Not found", { status: 404 });
  const token = await getAccessToken();
  if (!token) return new NextResponse("Sign in again.", { status: 401 });
  let response: Response;
  try {
    response = await fetch(`${platformEnv().apiUrl}/v1/w/${slug}/privacy/contacts/${id}/export`, {
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": newRequestId() },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return new NextResponse("The Onyx API is unavailable. Try again shortly.", { status: 503 });
  }
  if (!response.ok) {
    const status = [401, 403, 404].includes(response.status) ? response.status : 502;
    return new NextResponse(status === 404 ? "Not found" : "Export unavailable.", { status });
  }
  return new NextResponse(response.body, {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="contact-${id}.json"`,
      "Cache-Control": "private, no-store",
    },
  });
}
