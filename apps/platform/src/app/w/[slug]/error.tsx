"use client";

import { Button } from "@onyx/ui/components/button";
import { ErrorState } from "@onyx/ui/components/states";
import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Does nothing unless the browser DSN is set; the server side reports its own errors.
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);
  return (
    <div className="p-4 md:p-6">
      <ErrorState
        title="Something went wrong"
        description="The Onyx API could not complete this request. Try again shortly."
        action={
          <Button variant="outline" size="sm" onClick={reset} className="self-start">
            Try again
          </Button>
        }
      />
    </div>
  );
}
