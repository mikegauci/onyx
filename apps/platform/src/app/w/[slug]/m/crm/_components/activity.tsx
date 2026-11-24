import { type Activity, describeActivity, formatInZone } from "@/lib/crm";

/** The activity stream of one record, newest first. Times are in the workspace timezone. */
export function ActivityList({ items, timezone }: { items: Activity[]; timezone: string }) {
  if (items.length === 0) {
    return <p className="text-muted-foreground text-sm">No activity yet.</p>;
  }
  return (
    <ol className="flex flex-col gap-4" aria-label="Activity">
      {items.map((item) => (
        <li key={item.id} className="relative pl-5">
          <span
            aria-hidden
            className="bg-foreground/25 absolute top-1.5 left-0 size-2 rounded-full"
          />
          <p className="text-sm font-medium">{describeActivity(item)}</p>
          {item.body ? (
            <p className="bg-background mt-1 rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap">
              {item.body}
            </p>
          ) : null}
          <p className="text-muted-foreground mt-1 text-xs">
            {item.actor?.display_name ?? (item.actor ? "Former member" : "System")} ·{" "}
            <time dateTime={item.occurred_at}>{formatInZone(item.occurred_at, timezone)}</time>
          </p>
        </li>
      ))}
    </ol>
  );
}
