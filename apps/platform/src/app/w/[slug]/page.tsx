import { Badge } from "@onyx/ui/components/badge";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { type Workspace, apiGet } from "@/lib/api-client";

import { SignOutButton } from "../../sign-out-button";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ slug: string }> };

export default async function WorkspacePage({ params }: Props) {
  const { slug } = await params;
  const result = await apiGet<Workspace>(`/w/${encodeURIComponent(slug)}`);
  if (!result.ok) {
    if (result.status === "unauthenticated") redirect(`/login?next=/w/${encodeURIComponent(slug)}`);
    if (result.status === "not_found" || result.status === "forbidden") notFound();
    return (
      <main className="mx-auto max-w-xl px-6 py-16">
        <p role="alert">The Onyx API is unavailable. Try again shortly.</p>
      </main>
    );
  }
  const workspace = result.data;

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col gap-6 px-6 py-16">
      <header className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Link href="/workspaces" className="text-muted-foreground text-sm hover:underline">
            All workspaces
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight">{workspace.name}</h1>
        </div>
        <SignOutButton />
      </header>
      <p>
        Your role: <Badge variant="secondary">{workspace.role}</Badge>
      </p>
      <section aria-labelledby="modules-heading" className="flex flex-col gap-2">
        <h2 id="modules-heading" className="font-medium">
          Enabled modules
        </h2>
        {workspace.modules.length === 0 ? (
          <p className="text-muted-foreground">No modules enabled yet.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {workspace.modules.map((m) => (
              <li key={m}>
                <Badge variant="outline">{m}</Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
