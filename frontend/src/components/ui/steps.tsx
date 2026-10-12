import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

export interface StepItem {
  key: string;
  title: ReactNode;
  detail?: ReactNode;
  href?: string;
  current?: boolean;
  /** Short status shown beside the title, supplied by the caller. */
  badge?: ReactNode;
}

/** Numbered steps whose number, title and badge always stay inside the item and wrap. */
export function Steps({
  label,
  items,
  columns = false,
}: {
  label: string;
  items: StepItem[];
  /** Lay steps side by side from the sm breakpoint (otherwise stacked). */
  columns?: boolean;
}) {
  return (
    <nav aria-label={label}>
      <ol
        className={cx(
          "grid gap-3",
          columns && (items.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"),
        )}
      >
        {items.map((item, index) => {
          const body = (
            <>
              <span
                aria-hidden
                className={cx(
                  "flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold",
                  item.current
                    ? "border-amber bg-amber text-accent-ink"
                    : "border-edge-strong text-muted",
                )}
              >
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-ink text-sm font-semibold">{item.title}</span>
                  {item.badge}
                </span>
                {item.detail ? (
                  <span className="text-muted mt-1 block text-sm leading-5">{item.detail}</span>
                ) : null}
              </span>
            </>
          );
          const className = cx(
            "bg-raised flex h-full items-start gap-3 rounded-lg border p-3 transition-colors",
            item.current ? "border-amber" : "border-edge",
            item.href && !item.current && "hover:border-edge-strong",
          );
          return (
            <li key={item.key}>
              {item.href ? (
                <Link
                  href={item.href}
                  aria-current={item.current ? "step" : undefined}
                  className={className}
                >
                  {body}
                </Link>
              ) : (
                <div aria-current={item.current ? "step" : undefined} className={className}>
                  {body}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
