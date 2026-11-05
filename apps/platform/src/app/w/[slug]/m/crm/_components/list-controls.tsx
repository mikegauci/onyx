import { Button } from "@onyx/ui/components/button";
import { Input } from "@onyx/ui/components/input";
import Link from "next/link";
import type { ReactNode } from "react";

/** A GET search form (works without JavaScript) plus the section's primary action. */
export function ListToolbar({
  action,
  q,
  label,
  children,
  extra,
}: {
  action: string;
  q?: string;
  label: string;
  children?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <form action={action} method="get" role="search" className="flex flex-wrap items-end gap-2">
        {extra}
        <div className="flex flex-col gap-1">
          <label htmlFor="q" className="text-sm font-medium">
            {label}
          </label>
          <Input id="q" name="q" type="search" defaultValue={q} maxLength={100} className="w-64" />
        </div>
        <Button type="submit" variant="outline">
          Search
        </Button>
      </form>
      {children}
    </div>
  );
}

/** Keyset paging links: back to the first page, and the next page when there is one. */
export function Pager({
  base,
  params,
  cursor,
  nextCursor,
}: {
  base: string;
  params: Record<string, string | undefined>;
  cursor?: string;
  nextCursor?: string | null;
}) {
  const href = (extra: Record<string, string>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries({ ...params, ...extra })) {
      if (value) query.set(key, value);
    }
    const qs = query.toString();
    return qs ? `${base}?${qs}` : base;
  };
  if (!cursor && !nextCursor) return null;
  return (
    <div className="flex gap-2">
      {cursor ? (
        <Button asChild variant="outline" size="sm">
          <Link href={href({})}>First page</Link>
        </Button>
      ) : null}
      {nextCursor ? (
        <Button asChild variant="outline" size="sm">
          <Link href={href({ cursor: nextCursor })}>Next page</Link>
        </Button>
      ) : null}
    </div>
  );
}
