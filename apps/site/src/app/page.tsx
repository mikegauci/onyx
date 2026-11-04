import { Button } from "@onyx/ui/components/button";

import { siteEnv } from "@/lib/env";

export default function HomePage() {
  const { platformUrl } = siteEnv();

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6 py-16">
      <p className="text-muted-foreground text-sm font-medium tracking-widest uppercase">
        Onyx Studio
      </p>
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
        Business operations and AI automation, built around your team.
      </h1>
      <p className="text-muted-foreground text-lg">
        Onyx Platform connects enquiries, quotations, orders and fulfilment, with staff approval
        wherever it matters.
      </p>
      <div>
        <Button asChild size="lg">
          <a href={platformUrl}>Sign in to Onyx Platform</a>
        </Button>
      </div>
    </main>
  );
}
