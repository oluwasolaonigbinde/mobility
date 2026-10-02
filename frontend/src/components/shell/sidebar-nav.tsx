"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/lib/cx";

export interface NavItem {
  href: string;
  label: string;
  /** Match nested routes too (default true) */
  exact?: boolean;
  /** Optional section heading shown above the first item of a group (sidebar only). */
  group?: string;
  count?: number;
}

export function SidebarNav({
  items,
  horizontal = false,
}: {
  items: NavItem[];
  horizontal?: boolean;
}) {
  const pathname = usePathname();

  const list = (
    <>
      {items.map((item, index) => {
        const destination = item.href.split("?")[0];
        const active = item.exact
          ? pathname === destination
          : pathname === destination || pathname.startsWith(`${destination}/`);
        const heading =
          !horizontal && item.group && item.group !== items[index - 1]?.group ? item.group : null;
        return (
          <div key={item.href} className={horizontal ? "contents" : "flex flex-col"}>
            {heading ? <p className="micro text-faint mt-3 px-3 pb-1">{heading}</p> : null}
            <Link
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "micro rounded-lg px-3 py-2.5 whitespace-nowrap transition-colors",
                active ? "bg-raised text-amber" : "text-muted hover:bg-raised/60 hover:text-ink",
                horizontal && "px-3 py-2",
              )}
            >
              {item.label}
              {item.count ? (
                <span
                  className="bg-amber/15 text-amber ml-2 rounded-full px-2 py-0.5"
                  aria-label={`${item.count} waiting`}
                >
                  {item.count}
                </span>
              ) : null}
            </Link>
          </div>
        );
      })}
    </>
  );

  if (horizontal) return list;

  // min-h-0 + overflow keeps the account footer reachable on short laptop screens.
  return (
    <nav
      aria-label="Primary"
      className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3 pb-3"
    >
      {list}
    </nav>
  );
}
