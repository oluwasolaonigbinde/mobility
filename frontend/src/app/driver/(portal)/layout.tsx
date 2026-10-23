import type { ReactNode } from "react";
import Link from "next/link";
import { TabBar } from "@/components/driver/tab-bar";
import { ServiceWorkerRegister } from "@/components/driver/sw-register";
import { requireRole } from "@/lib/auth/current-user";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { BrandWordmark } from "@/components/shell/brand-wordmark";

export default async function DriverPortalLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("driver");

  return (
    <div className="driver-portal mx-auto flex min-h-dvh w-full max-w-2xl flex-col">
      <ServiceWorkerRegister />
      <header
        className="border-edge bg-bg/90 sticky top-0 z-40 flex items-center justify-between gap-3 border-b px-4 py-3 backdrop-blur"
        style={{ paddingTop: "max(env(safe-area-inset-top), 0.75rem)" }}
      >
        <Link href="/driver" className="font-display shrink-0 text-lg font-semibold tracking-tight">
          <BrandWordmark />
        </Link>
        <div className="flex shrink-0 items-center gap-1 whitespace-nowrap sm:gap-3">
          <Link
            href="/driver/help"
            className="text-muted hover:text-ink rounded px-2 py-1 text-sm font-medium transition-colors"
          >
            Help
          </Link>
          <NotificationCenter sessionScope={me.user.id} compact />
          <span className="text-ink hidden px-2 text-sm font-medium sm:inline">
            {me.user.full_name.split(" ")[0]}
          </span>
        </div>
      </header>

      <main className="flex-1 px-4 pt-5 pb-[calc(6rem+env(safe-area-inset-bottom))]">
        {children}
      </main>

      <TabBar />
    </div>
  );
}
