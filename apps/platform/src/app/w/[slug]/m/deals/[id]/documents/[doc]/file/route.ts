import { NextResponse } from "next/server";

import { newRequestId } from "@/lib/api-client";
import { platformEnv } from "@/lib/env";
import { getAccessToken } from "@/lib/supabase/server";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;
const TYPES = new Set(["application/pdf", "image/jpeg", "image/png", "image/heic"]);

/**
 * Streams a deal document from the API as the signed-in user (VA-007). The API checks
 * membership, the module and `deals.documents`, and audits each opening; this only forwards
 * the user's token. Never cached.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string; id: string; doc: string }> },
) {
  const { slug, id, doc } = await params;
  if (!SLUG.test(slug) || !UUID.test(id) || !UUID.test(doc)) {
    return new NextResponse("Not found", { status: 404 });
  }
  const token = await getAccessToken();
  if (!token) return new NextResponse("Sign in again.", { status: 401 });
  let response: Response;
  try {
    response = await fetch(
      `${platformEnv().apiUrl}/v1/w/${slug}/deals/${id}/documents/${doc}/file`,
      {
        headers: { Authorization: `Bearer ${token}`, "X-Request-ID": newRequestId() },
        cache: "no-store",
        signal: AbortSignal.timeout(30_000),
      },
    );
  } catch {
    return new NextResponse("The Onyx API is unavailable. Try again shortly.", { status: 503 });
  }
  const type = response.headers.get("content-type") ?? "";
  if (!response.ok || !TYPES.has(type)) {
    const status = [401, 403, 404].includes(response.status) ? response.status : 502;
    return new NextResponse(status === 404 ? "Not found" : "Document unavailable.", { status });
  }
  return new NextResponse(response.body, {
    status: 200,
    headers: {
      "Content-Type": type,
      // Shown in the browser (PDF or image), never sniffed as anything else.
      "Content-Disposition": (response.headers.get("content-disposition") ?? "").replace(
        /^attachment/,
        "inline",
      ),
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
