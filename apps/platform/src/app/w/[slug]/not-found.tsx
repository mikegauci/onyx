import { Button } from "@onyx/ui/components/button";
import { EmptyState } from "@onyx/ui/components/states";
import { SearchX } from "lucide-react";
import Link from "next/link";

export default function WorkspaceNotFound() {
  return (
    <div className="p-4 md:p-6">
      <EmptyState
        icon={SearchX}
        title="Not found"
        description="This page does not exist, or you do not have access to it."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href="/workspaces">Your workspaces</Link>
          </Button>
        }
      />
    </div>
  );
}
