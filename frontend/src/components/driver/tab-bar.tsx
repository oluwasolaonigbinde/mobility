"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/lib/cx";

const TABS = [
  { href: "/driver", label: "Home", icon: "⌂", exact: true },
  { href: "/driver/assignments", label: "Jobs", icon: "▤" },
  { href: "/driver/track", label: "Track", icon: "◉" },
  { href: "/driver/earnings", label: "Earnings", icon: "₦" },
  { href: "/driver/profile", label: "Profile", icon: "◍" },
] as const;

/** App-style bottom tab bar — thumb-reach navigation, safe-area aware. */
export function TabBar() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Driver app"
      className="border-edge bg-panel/95 fixed inset-x-0 bottom-0 z-50 border-t backdrop-blur"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="mx-auto flex max-w-md">
        {TABS.map((tab) => {
          const exact = "exact" in tab && tab.exact;
          const active = exact
            ? pathname === tab.href
            : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "flex flex-1 flex-col items-center gap-0.5 py-2.5 transition-colors",
                active ? "text-amber" : "text-faint hover:text-muted",
              )}
            >
              <span aria-hidden className="text-lg leading-none">
                {tab.icon}
              </span>
              <span className="micro">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
