import { ThemeToggle } from "@onyx/ui/components/theme-toggle";
import { Badge } from "@onyx/ui/components/badge";
import Link from "next/link";
import { redirect } from "next/navigation";

import { withApi } from "@/lib/api-client";

import { SignOutButton } from "../sign-out-button";

export const dynamic = "force-dynamic";

export default async function WorkspacesPage() {
  const me = await withApi((api) => api.GET("/v1/me"));
  if (!me.ok && me.status === "unauthenticated") redirect("/login?next=/workspaces");

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col gap-6 px-6 py-16">
      <ThemeToggle className="fixed top-4 right-4" />
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">Your workspaces</h1>
        <SignOutButton />
      </header>
      {!me.ok ? (
        <p role="alert">The Onyx API is unavailable. Try again shortly.</p>
      ) : me.data.workspaces.length === 0 ? (
        <p className="text-muted-foreground">
          Signed in as {me.data.user.email}. You are not a member of any workspace yet; ask an admin
          to invite you.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {me.data.workspaces.map((w) => (
            <li key={w.slug}>
              <Link
                href={`/w/${w.slug}`}
                className="hover:bg-muted focus-visible:ring-ring flex items-center justify-between rounded-md border px-4 py-3 focus-visible:ring-2 focus-visible:outline-none"
              >
                <span>{w.name}</span>
                <Badge variant="secondary">{w.role}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
