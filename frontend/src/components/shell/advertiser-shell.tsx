import Link from "next/link";
import type { ReactNode } from "react";
import type { MeResponse } from "@/lib/auth/current-user";
import { SessionLogoutButton } from "@/components/driver/logout-button";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { BrandWordmark } from "./brand-wordmark";
import { AdvertiserNavigation } from "./advertiser-navigation";

export function AdvertiserShell({ me, children }: { me: MeResponse; children: ReactNode }) {
  const org = me.advertiser_organization;
  const account = (
    <>
      <p className="truncate text-sm font-semibold">{me.user.full_name}</p>
      <p className="text-muted mt-1 truncate text-sm">{org?.name}</p>
      <SessionLogoutButton
        label="Sign out"
        className="text-muted hover:text-coral mt-3 min-h-11 text-sm font-medium"
      />
    </>
  );
  return (
    <div className="advertiser-portal flex min-h-dvh flex-1">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded focus:bg-white focus:p-3"
      >
        Skip to content
      </a>
      <AdvertiserNavigation account={account} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="portal-top relative flex shrink-0 items-start justify-between gap-3 px-5 pt-5 md:px-10 md:pt-7">
          <div className="ml-14 md:hidden">
            <Link href="/advertiser">
              <BrandWordmark />
            </Link>
          </div>
          <p className="text-ink hidden text-base font-semibold md:block">{org?.name}</p>
          <div className="flex items-center gap-3">
            <NotificationCenter
              compact
              sessionScope={me.user.id}
              canManageAdvertiserPreferences={org?.membership_role === "advertiser"}
            />
          </div>
        </header>
        <main id="main" className="portal-main relative min-w-0 flex-1 px-5 pb-12 md:px-10">
          {children}
        </main>
      </div>
    </div>
  );
}
