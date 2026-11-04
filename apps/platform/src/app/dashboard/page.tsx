import { getApiHealth } from "@/lib/api-health";

import { ApiStatus } from "./api-status";

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default async function DashboardPage() {
  const health = await getApiHealth(API_URL);

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
