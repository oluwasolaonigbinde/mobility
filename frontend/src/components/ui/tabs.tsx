"use client";

import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import { cx } from "@/lib/cx";

export interface TabItem {
  href: string;
  label: ReactNode;
  active: boolean;
  /** Optional count shown beside the label. */
  count?: number;
}

/**
 * Primary view switch for a page ("Complaints / Driver contact"). URL-driven links with
 * aria-current; spread across the width on desktop and scrollable on a phone.
 */
export function ViewTabs({ label, items }: { label: string; items: TabItem[] }) {
  const activeRef = useRef<HTMLAnchorElement>(null);
  const activeHref = items.find((item) => item.active)?.href;
  useEffect(() => {
    activeRef.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [activeHref]);
  return (
    <nav aria-label={label} className="border-edge mb-5 overflow-x-auto overflow-y-hidden border-b">
      <div className="flex min-w-max sm:min-w-0">
        {items.map((item) => (
          <Link
            key={item.href}
            ref={item.active ? activeRef : undefined}
            href={item.href}
            data-tab
            aria-current={item.active ? "page" : undefined}
            className={cx(
              "-mb-px flex flex-1 items-center justify-center gap-2 border-b-2 px-4 py-3 text-[0.9375rem] font-medium whitespace-nowrap transition-colors sm:px-5",
              item.active
                ? "border-amber text-ink"
                : "text-muted hover:text-ink hover:border-edge-strong border-transparent",
            )}
          >
            {item.label}
            {item.count !== undefined ? <TabCount value={item.count} active={item.active} /> : null}
          </Link>
        ))}
      </div>
    </nav>
  );
}

/** Secondary filters within a view ("Needs a reply / Resolved / All"). Wraps on a phone. */
export function FilterChips({
  label,
  items,
  visibleLabel,
}: {
  label: string;
  items: TabItem[];
  /** Short visible lead-in such as "Show". */
  visibleLabel?: string;
}) {
  return (
    <nav aria-label={label} className="mb-5 flex flex-wrap items-center gap-2">
      {visibleLabel ? <span className="text-muted mr-1 text-sm">{visibleLabel}</span> : null}
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          data-chip
          aria-current={item.active ? "page" : undefined}
          className={cx(
            "inline-flex h-9 items-center gap-2 rounded-full border px-4 text-sm font-medium transition-colors",
            item.active
              ? "border-amber bg-amber text-accent-ink"
              : "border-edge bg-raised text-muted hover:border-edge-strong hover:text-ink",
          )}
        >
          {item.label}
          {item.count !== undefined ? <TabCount value={item.count} active={item.active} /> : null}
        </Link>
      ))}
    </nav>
  );
}

function TabCount({ value, active }: { value: number; active: boolean }) {
  return (
    <span
      className={cx(
        "rounded-full px-2 py-0.5 text-xs tabular-nums",
        active ? "bg-ink/10" : "bg-edge/70 text-muted",
      )}
    >
      {value}
    </span>
  );
}
