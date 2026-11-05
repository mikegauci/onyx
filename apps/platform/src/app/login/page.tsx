import { ThemeToggle } from "@onyx/ui/components/theme-toggle";
import { Button } from "@onyx/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@onyx/ui/components/card";
import { Input } from "@onyx/ui/components/input";
import { Label } from "@onyx/ui/components/label";

import { supabaseEnv } from "@/lib/supabase/env";

import { sendMagicLink } from "./actions";

const ERRORS: Record<string, string> = {
  email: "Enter a valid email address.",
  send: "We could not send the link. Wait a minute and try again.",
  link: "That sign-in link is invalid or has expired. Request a new one.",
  unconfigured: "Sign-in is not configured for this environment.",
};

type Props = { searchParams: Promise<{ next?: string; error?: string; sent?: string }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next = "", error, sent } = await searchParams;
  const configured = supabaseEnv() !== null;
  const message = error ? (ERRORS[error] ?? ERRORS.send) : null;

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <ThemeToggle className="fixed top-4 right-4" />
      <Card>
        <CardHeader>
          <CardTitle>Sign in to Onyx</CardTitle>
          <CardDescription>We will email you a one-time sign-in link.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
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
                  required
                  disabled={!configured}
                  aria-describedby={message ? "login-error" : undefined}
                  aria-invalid={error === "email" ? true : undefined}
                />
              </div>
              {(message || !configured) && (
                <p id="login-error" role="alert" className="text-destructive text-sm">
                  {message ?? ERRORS.unconfigured}
                </p>
              )}
              <Button type="submit" disabled={!configured}>
                Email me a link
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
