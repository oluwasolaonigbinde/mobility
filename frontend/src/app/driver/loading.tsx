import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Loading">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-36" />
      <Skeleton className="h-36" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
