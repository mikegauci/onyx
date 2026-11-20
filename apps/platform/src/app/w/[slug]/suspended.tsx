import { Button } from "@onyx/ui/components/button";
import Link from "next/link";

/** Shown instead of the workspace while Onyx has suspended it. Nothing has been deleted. */
export function SuspendedWorkspace({ name, hasOthers }: { name: string; hasOthers: boolean }) {
  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-4 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">This workspace is suspended</h1>
      <p className="text-sm">
        {name} is suspended, so it cannot be opened and incoming messages are not received. Nothing
        has been deleted. Contact Onyx support to reactivate it.
      </p>
      <div className="flex flex-wrap gap-3">
        {hasOthers ? (
          <Button asChild variant="outline">
            <Link href="/workspaces">Your other workspaces</Link>
          </Button>
        ) : null}
        <Button asChild variant="ghost">
          <Link href="/login">Sign in as someone else</Link>
        </Button>
      </div>
    </main>
  );
}
