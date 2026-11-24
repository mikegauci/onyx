import { Badge } from "@onyx/ui/components/badge";
import { Eyebrow } from "@onyx/ui/components/page";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AuthFrame } from "@/components/auth-frame";
import { withApi } from "@/lib/api-client";

import { SignOutButton } from "../sign-out-button";

export const dynamic = "force-dynamic";

export default async function WorkspacesPage() {
  const me = await withApi((api) => api.GET("/v1/me"));
  if (!me.ok && me.status === "unauthenticated") redirect("/login?next=/workspaces");

  return (
    <AuthFrame width="xl">
      <header className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-3">
          <Eyebrow>Onyx Platform</Eyebrow>
          <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
            Your workspaces
          </h1>
        </div>
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
        <ul className="bg-card/70 divide-y overflow-hidden rounded-2xl border backdrop-blur-xl">
          {me.data.workspaces.map((w) => (
            <li key={w.slug}>
              <Link
                href={`/w/${w.slug}`}
                className="group hover:bg-foreground/[0.04] focus-visible:ring-ring flex items-center gap-4 px-5 py-4 transition-colors focus-visible:ring-2 focus-visible:outline-none focus-visible:ring-inset"
              >
                <span className="bg-brand/15 text-brand flex size-9 items-center justify-center rounded-xl text-sm font-medium">
                  {w.name.slice(0, 1).toUpperCase()}
                </span>
                <span className="flex-1 truncate">{w.name}</span>
                {w.status === "suspended" ? <Badge variant="warning">Suspended</Badge> : null}
                <Badge variant="secondary" className="capitalize">
                  {w.role}
                </Badge>
                <ArrowRight
                  aria-hidden
                  className="text-muted-foreground group-hover:text-brand size-4 transition-[color,transform] group-hover:translate-x-0.5"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {me.ok && me.data.is_platform_admin ? (
        <Link href="/admin" className="text-brand self-start text-sm font-medium hover:underline">
          Open platform admin
        </Link>
      ) : null}
    </AuthFrame>
  );
}
