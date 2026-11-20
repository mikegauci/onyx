"use client";

import { Button } from "@onyx/ui/components/button";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../form-status";
import { openPortal, startCheckout } from "./actions";

export function ChoosePlan({
  slug,
  plan,
  name,
  current,
}: {
  slug: string;
  plan: "starter" | "growth";
  name: string;
  current: boolean;
}) {
  const [state, action, pending] = useActionState(startCheckout.bind(null, slug, plan), IDLE);
  return (
    <form action={action} className="flex flex-col gap-2">
      <Button type="submit" disabled={pending || current} variant={current ? "outline" : "default"}>
        {current ? "Current plan" : pending ? "Opening checkout…" : `Choose ${name}`}
      </Button>
      <FormStatus state={state} />
    </form>
  );
}

export function ManageBilling({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(openPortal.bind(null, slug), IDLE);
  return (
    <form action={action} className="flex flex-col gap-2">
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        {pending ? "Opening…" : "Manage billing"}
      </Button>
      <FormStatus state={state} />
    </form>
  );
}
