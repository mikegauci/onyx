"use client";

import { Button } from "@onyx/ui/components/button";
import { ErrorState } from "@onyx/ui/components/states";

export default function WorkspaceError({ reset }: { error: Error; reset: () => void }) {
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
