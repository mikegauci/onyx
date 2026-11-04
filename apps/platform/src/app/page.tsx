import { Button } from "@onyx/ui/components/button";
import Link from "next/link";

export default function PlatformHomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Onyx Platform</h1>
      <p className="text-muted-foreground">
        Sign-in arrives in a later release. This placeholder confirms the dashboard app runs.
      </p>
      <div>
        <Button asChild>
          <Link href="/dashboard">Open dashboard</Link>
        </Button>
      </div>
    </main>
  );
}
