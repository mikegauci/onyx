import { OnyxLogo } from "@onyx/ui/components/onyx-logo";
import type { Metadata } from "next";

import { platformEnv } from "@/lib/env";

import { UploadList, type UploadPage } from "./upload-list";

// The token is the credential: never index this page, and never pass it on as a referrer.
export const metadata: Metadata = {
  title: "Upload your documents",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ token: string }> };

const TOKEN = /^[A-Za-z0-9_-]{20,100}$/;

async function load(token: string): Promise<UploadPage | null> {
  if (!TOKEN.test(token)) return null;
  try {
    const response = await fetch(`${platformEnv().apiUrl}/v1/public/uploads/${token}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
    return response.ok ? ((await response.json()) as UploadPage) : null;
  } catch {
    return null;
  }
}

export default async function CustomerUploadPage({ params }: Props) {
  const { token } = await params;
  const page = await load(token);
  return (
    <div className="bg-background flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b px-5 py-4">
        <span className="text-sm font-medium">{page?.business_name ?? "Document upload"}</span>
        <OnyxLogo product="Platform" className="text-muted-foreground h-4" />
      </header>
      <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-6 px-5 py-8">
        {page ? (
          <UploadList token={token} apiUrl={platformEnv().apiUrl} initial={page} />
        ) : (
          <div className="flex flex-col gap-2" role="status">
            <h1 className="text-2xl font-light tracking-tight">This link is not valid</h1>
            <p className="text-muted-foreground text-sm">
              It may have expired, or the business made a new one. Ask them to send you a new link.
            </p>
          </div>
        )}
      </main>
      <footer className="text-muted-foreground px-5 py-4 text-center text-xs">
        Your files go privately to the business. Only their staff can see them.
      </footer>
    </div>
  );
}
