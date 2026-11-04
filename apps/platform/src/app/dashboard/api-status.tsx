import type { ApiHealth } from "@/lib/api-health";

export function ApiStatus({ health }: { health: ApiHealth }) {
  const ok = health.state === "ok";
  return (
    <div role="status" className="bg-card flex items-center gap-3 rounded-lg border p-4">
      <span
        aria-hidden="true"
        className={ok ? "size-2.5 rounded-full bg-emerald-500" : "size-2.5 rounded-full bg-red-500"}
      />
      <span className="font-medium">API: {ok ? "ok" : "unreachable"}</span>
      <span className="text-muted-foreground text-sm">
        {ok ? `${health.service} v${health.version}` : health.reason}
      </span>
    </div>
  );
}
