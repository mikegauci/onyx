import type { ReactNode } from "react";

import { BackLink } from "./back-link";

/** The top of a record page: back link, title, status badges, key facts and actions. */
export function RecordHeader({
  back,
  title,
  badges,
  meta,
  actions,
}: {
  back: { href: string; label: string };
  title: ReactNode;
  badges?: ReactNode;
  /** Short facts shown under the title, e.g. email · phone · customer. */
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4">
      <BackLink href={back.href}>{back.label}</BackLink>
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-light tracking-[-0.02em] text-balance">{title}</h2>
            {badges}
          </div>
          {meta ? (
            <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
              {meta}
            </div>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </div>
  );
}

/** Main column plus a side column (activity, history) that stacks under it on phones. */
export function RecordLayout({ main, aside }: { main: ReactNode; aside?: ReactNode }) {
  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="flex min-w-0 flex-col gap-6">{main}</div>
      {aside ? <aside className="flex min-w-0 flex-col gap-4">{aside}</aside> : null}
    </div>
  );
}
