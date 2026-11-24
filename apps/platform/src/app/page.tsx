import { Button } from "@onyx/ui/components/button";
import { Eyebrow } from "@onyx/ui/components/page";
import Link from "next/link";

import { AuthFrame } from "@/components/auth-frame";

export default function PlatformHomePage() {
  return (
    <AuthFrame>
      <Eyebrow>Onyx Platform</Eyebrow>
      <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
        Onyx Platform
      </h1>
      <p className="text-muted-foreground">Sign in with your work email to open your workspaces.</p>
      <div className="flex gap-3">
        <Button asChild>
          <Link href="/workspaces">Sign in</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/dashboard">API status</Link>
        </Button>
      </div>
    </AuthFrame>
  );
}
