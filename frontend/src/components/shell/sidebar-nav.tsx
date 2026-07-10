"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/lib/cx";

export interface NavItem {
  href: string;
  label: string;
  /** Match nested routes too (default true) */
  exact?: boolean;
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
      {items.map((item) => {
        const active = item.exact
          ? pathname === item.href
          : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "micro rounded-lg px-3 py-2.5 whitespace-nowrap transition-colors",
              active ? "bg-raised text-amber" : "text-muted hover:bg-raised/60 hover:text-ink",
              horizontal && "px-3 py-2",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </>
  );

  if (horizontal) return list;

  return (
    <nav aria-label="Primary" className="flex flex-col gap-1 px-3">
      {list}
    </nav>
  );
}
