import Link from "next/link";
import type { ReactNode } from "react";
import type { MeResponse } from "@/lib/auth/current-user";
import { signOutAction } from "@/lib/auth/actions";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { SidebarNav, type NavItem } from "./sidebar-nav";

export type { NavItem };

const roleLabel: Record<string, string> = {
  admin: "Admin / Ops",
  advertiser: "Advertiser",
  driver: "Driver",
};

/**
 * Shared authenticated shell: icon-free sidebar rail (mono labels, like the
 * prototype), sticky topbar with identity context, content well.
 */
export function AppShell({
  me,
  nav,
  children,
}: {
  me: MeResponse;
  nav: NavItem[];
  children: ReactNode;
}) {
  const org = me.advertiser_organization;
  const canManageAdvertiserPreferences =
    me.user.role === "advertiser" &&
    (org?.membership_role === "owner" || org?.membership_role === "manager");

  return (
    <div className="flex min-h-dvh flex-1">
      <a
        href="#main"
        className="focus:bg-amber focus:text-bg sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>

      {/* Sidebar */}
      <aside className="border-edge bg-panel sticky top-0 hidden h-dvh w-52 shrink-0 flex-col border-r md:flex">
        <Link href="/" className="flex items-center gap-2 px-5 pt-5 pb-6">
          <span className="font-display text-amber text-lg font-bold" aria-hidden>
            C
          </span>
          <span className="font-display text-lg font-semibold tracking-tight">
            Cardvert<span className="text-amber">.</span>
          </span>
        </Link>
        <SidebarNav items={nav} />
        <div className="border-edge mt-auto border-t p-4">
          <p className="truncate text-sm font-medium">{me.user.full_name}</p>
          <p className="micro text-faint mt-0.5">{roleLabel[me.user.role] ?? me.user.role}</p>
          <form action={signOutAction} className="mt-3">
            <button type="submit" className="micro text-muted hover:text-coral transition-colors">
              Sign out →
            </button>
          </form>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="border-edge bg-bg/85 sticky top-0 z-40 flex h-14 items-center justify-between border-b px-4 backdrop-blur md:px-6">
          <div className="flex items-center gap-3 md:hidden">
            <Link href="/" className="font-display text-lg font-semibold">
              Cardvert<span className="text-amber">.</span>
            </Link>
          </div>
          <div className="micro text-muted hidden md:block">
            {org ? (
              <>
                {org.name} · <span className="text-amber">{org.currency}</span>
              </>
            ) : (
              <>Network · {roleLabel[me.user.role] ?? me.user.role}</>
            )}
          </div>
          <div className="micro text-muted flex items-center gap-2">
            <NotificationCenter
              canManageAdvertiserPreferences={canManageAdvertiserPreferences}
              sessionScope={me.user.id}
            />
            <span aria-label="Workspace context">Workspace</span>
          </div>
        </header>

        {/* Mobile nav */}
        <nav
          aria-label="Primary"
          className="border-edge bg-panel flex gap-1 overflow-x-auto border-b px-2 py-2 md:hidden"
        >
          <SidebarNav items={nav} horizontal />
        </nav>

        <main id="main" className="flex-1 p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
