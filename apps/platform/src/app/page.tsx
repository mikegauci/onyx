import { Button } from "@onyx/ui/components/button";
import Link from "next/link";

export default function PlatformHomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Onyx Platform</h1>
      <p className="text-muted-foreground">Sign in with your work email to open your workspaces.</p>
      <div className="flex gap-3">
        <Button asChild>
          <Link href="/workspaces">Sign in</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/dashboard">API status</Link>
        </Button>
      </div>
    </main>
  );
}
