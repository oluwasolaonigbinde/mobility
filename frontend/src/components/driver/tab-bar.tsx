"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/lib/cx";
import { PortalIcon } from "@/components/brand/portal-icon";

const TABS = [
  { href: "/driver", label: "Home", icon: "home", exact: true },
  { href: "/driver/assignments", label: "Jobs", icon: "megaphone" },
  { href: "/driver/track", label: "Track", icon: "pin" },
  { href: "/driver/earnings", label: "Earnings", icon: "wallet" },
  { href: "/driver/profile", label: "Profile", icon: "user" },
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
      <div className="mx-auto flex max-w-2xl">
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
                active ? "text-amber" : "text-muted hover:text-ink",
              )}
            >
              <span aria-hidden className="text-lg leading-none">
                <PortalIcon name={tab.icon} />
              </span>
              <span className="text-xs font-medium">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
