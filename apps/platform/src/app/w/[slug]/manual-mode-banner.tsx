import { Hand } from "lucide-react";
import Link from "next/link";

/** Shown on every workspace page while manual mode is on (PR-018 pilot controls). */
export function ManualModeBanner({
  reason,
  settingsHref,
}: {
  reason: string | null;
  settingsHref: string | null;
}) {
  return (
    <div
      role="status"
      className="border-warning/40 bg-warning/[0.08] flex flex-col gap-2 rounded-2xl border px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2.5">
        <Hand aria-hidden className="text-warning mt-0.5 size-4 shrink-0" />
        <span>
          <strong className="font-medium">Manual mode is on.</strong> Onyx is not drafting or
          sending anything automatically. Messages still arrive and staff reply as normal.
          {reason ? <span className="text-muted-foreground"> Reason: {reason}</span> : null}
        </span>
      </p>
      {settingsHref ? (
        <Link
          href={settingsHref}
          className="text-brand shrink-0 font-medium underline-offset-4 hover:underline"
        >
          Pilot controls
        </Link>
      ) : null}
    </div>
  );
}
