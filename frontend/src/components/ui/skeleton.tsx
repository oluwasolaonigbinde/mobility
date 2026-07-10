import { cx } from "@/lib/cx";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("bg-raised animate-pulse rounded-lg", className)} aria-hidden />;
}

/** Standard page-loading composition: header line + KPI row + content block. */
export function PageSkeleton() {
  return (
    <div className="mx-auto max-w-6xl" role="status" aria-label="Loading">
      <Skeleton className="mb-2 h-9 w-64" />
      <Skeleton className="mb-8 h-4 w-40" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="mt-6 h-72" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
