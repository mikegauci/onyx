import { getApiHealth } from "@/lib/api-health";
import { platformEnv } from "@/lib/env";

import { ApiStatus } from "./api-status";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const health = await getApiHealth(platformEnv().apiUrl);

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
      <p className="text-muted-foreground">
        Placeholder. Workspaces, sign-in and modules arrive in later releases.
      </p>
      <ApiStatus health={health} />
    </main>
  );
}
