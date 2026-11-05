import { Skeleton } from "@onyx/ui/components/skeleton";

export default function WorkspaceLoading() {
  return (
    <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-4 p-4 md:p-6">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-48" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    </div>
  );
}
