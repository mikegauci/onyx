import { Button } from "@onyx/ui/components/button";
import { Input } from "@onyx/ui/components/input";
import { Label } from "@onyx/ui/components/label";
import { Eyebrow } from "@onyx/ui/components/page";
import type { Metadata } from "next";

import { AuthFrame } from "@/components/auth-frame";
import { supabaseEnv } from "@/lib/supabase/env";

import { sendMagicLink } from "./actions";

const ERRORS: Record<string, string> = {
  email: "Enter a valid email address.",
  send: "We could not send the link. Wait a minute and try again.",
  link: "That sign-in link is invalid or has expired. Request a new one.",
  unconfigured: "Sign-in is not configured for this environment.",
};

export const metadata: Metadata = { title: "Sign in" };

type Props = { searchParams: Promise<{ next?: string; error?: string; sent?: string }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next = "", error, sent } = await searchParams;
  const configured = supabaseEnv() !== null;
  const message = error ? (ERRORS[error] ?? ERRORS.send) : null;

  return (
    <AuthFrame>
      <div className="flex flex-col gap-3">
        <Eyebrow>Sign in</Eyebrow>
        <h1 className="text-[clamp(2rem,6vw,2.8rem)] leading-[1.05] font-light tracking-[-0.04em]">
          Welcome back
        </h1>
        <p className="text-muted-foreground text-sm">
          We will email you a one-time sign-in link. Open it in this browser.
        </p>
      </div>
      <div className="bg-card/70 rounded-2xl border p-6 backdrop-blur-xl">
        {sent ? (
          <p role="status" className="text-sm">
            Check your email for a sign-in link. You can close this tab.
          </p>
        ) : (
          <form action={sendMagicLink} className="flex flex-col gap-4">
            <input type="hidden" name="next" value={next} />
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Work email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                required
                disabled={!configured}
                className="h-11"
                aria-describedby={message ? "login-error" : undefined}
                aria-invalid={error === "email" ? true : undefined}
              />
            </div>
            {(message || !configured) && (
              <p id="login-error" role="alert" className="text-destructive text-sm">
                {message ?? ERRORS.unconfigured}
              </p>
            )}
            <Button type="submit" size="lg" disabled={!configured}>
              Email me a link →
            </Button>
          </form>
        )}
      </div>
    </AuthFrame>
  );
}
