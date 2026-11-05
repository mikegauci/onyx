import { ThemeToggle } from "@onyx/ui/components/theme-toggle";

import { AcceptForm } from "./accept-form";

type Props = { searchParams: Promise<{ token?: string }> };

export const dynamic = "force-dynamic";

export default async function AcceptInvitationPage({ searchParams }: Props) {
  const { token = "" } = await searchParams;
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6 py-16">
      <ThemeToggle className="fixed top-4 right-4" />
      <h1 className="text-2xl font-semibold tracking-tight">Join a workspace</h1>
      <p className="text-muted-foreground">
        Accept this invitation to join the workspace with the role it grants. It only works for the
        email address it was sent to.
      </p>
      <AcceptForm token={token} />
    </main>
  );
}
