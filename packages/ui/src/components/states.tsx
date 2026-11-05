import type { LucideIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "../lib/utils";

type StateProps = {
  icon?: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
};

/** Empty state: icon, one sentence and an optional primary action. */
export function EmptyState({ icon: Icon, title, description, action, className }: StateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-10 text-center",
        className,
      )}
    >
      {Icon ? <Icon aria-hidden className="text-muted-foreground size-8" /> : null}
      <h2 className="font-medium">{title}</h2>
      {description ? <p className="text-muted-foreground max-w-sm text-sm">{description}</p> : null}
      {action}
    </div>
  );
}

/** Error state with an optional request id so staff can quote it to support. */
export function ErrorState({
  title,
  description,
  action,
  requestId,
  className,
}: Omit<StateProps, "icon"> & { requestId?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        "border-destructive/40 flex flex-col gap-2 rounded-lg border p-6 text-sm",
        className,
      )}
    >
      <h2 className="text-base font-medium">{title}</h2>
      {description ? <p className="text-muted-foreground">{description}</p> : null}
      {requestId ? (
        <p className="text-muted-foreground font-mono text-xs">Reference: {requestId}</p>
      ) : null}
      {action}
    </div>
  );
}
