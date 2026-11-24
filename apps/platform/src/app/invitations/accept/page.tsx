import { Eyebrow } from "@onyx/ui/components/page";

import { AuthFrame } from "@/components/auth-frame";

import { AcceptForm } from "./accept-form";

type Props = { searchParams: Promise<{ token?: string }> };

export const dynamic = "force-dynamic";

export default async function AcceptInvitationPage({ searchParams }: Props) {
  const { token = "" } = await searchParams;
  return (
    <AuthFrame>
      <Eyebrow>Invitation</Eyebrow>
      <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
        Join a workspace
      </h1>
      <p className="text-muted-foreground">
        Accept this invitation to join the workspace with the role it grants. It only works for the
        email address it was sent to.
      </p>
      <div className="bg-card/70 rounded-2xl border p-6 backdrop-blur-xl">
        <AcceptForm token={token} />
      </div>
    </AuthFrame>
  );
}
