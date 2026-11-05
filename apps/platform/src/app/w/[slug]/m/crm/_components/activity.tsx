import { type Activity, describeActivity, formatInZone } from "@/lib/crm";

/** The activity stream of one record, newest first. Times are in the workspace timezone. */
export function ActivityList({ items, timezone }: { items: Activity[]; timezone: string }) {
  if (items.length === 0) {
    return <p className="text-muted-foreground text-sm">No activity yet.</p>;
  }
  return (
    <ol className="flex flex-col gap-3" aria-label="Activity">
      {items.map((item) => (
        <li key={item.id} className="border-l-2 pl-3">
          <p className="text-sm font-medium">{describeActivity(item)}</p>
          {item.body ? <p className="text-sm whitespace-pre-wrap">{item.body}</p> : null}
          <p className="text-muted-foreground text-xs">
            {item.actor?.display_name ?? (item.actor ? "Former member" : "System")} ·{" "}
            <time dateTime={item.occurred_at}>{formatInZone(item.occurred_at, timezone)}</time>
          </p>
        </li>
      ))}
    </ol>
  );
}
