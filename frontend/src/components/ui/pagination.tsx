import Link from "next/link";
import { cx } from "@/lib/cx";

/**
 * Offset pagination driven by searchParams — server-rendered, so the URL is
 * always shareable and the back button behaves.
 */
export function Pagination({
  total,
  limit,
  offset,
  hrefFor,
}: {
  total: number;
  limit: number;
  offset: number;
  hrefFor: (offset: number) => string;
}) {
  if (total <= limit) return null;

  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  const prev = offset - limit >= 0 ? offset - limit : null;
  const next = offset + limit < total ? offset + limit : null;

  const linkClass = (enabled: boolean) =>
    cx(
      "micro rounded-lg border px-3 py-2 transition-colors",
      enabled
        ? "border-edge text-muted hover:border-edge-strong hover:text-ink"
        : "pointer-events-none border-edge/50 text-faint",
    );

  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between">
      <Link
        href={prev !== null ? hrefFor(prev) : "#"}
        aria-disabled={prev === null}
        className={linkClass(prev !== null)}
      >
        ← Prev
      </Link>
      <span className="micro text-faint">
        Page {page} of {pages} · {total} total
      </span>
      <Link
        href={next !== null ? hrefFor(next) : "#"}
        aria-disabled={next === null}
        className={linkClass(next !== null)}
      >
        Next →
      </Link>
    </nav>
  );
}
