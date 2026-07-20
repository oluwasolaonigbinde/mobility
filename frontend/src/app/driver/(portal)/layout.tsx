import type { ReactNode } from "react";
import { TabBar } from "@/components/driver/tab-bar";
import { ServiceWorkerRegister } from "@/components/driver/sw-register";
import { signOutAction } from "@/lib/auth/actions";
import { requireRole } from "@/lib/auth/current-user";

export default async function DriverPortalLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("driver");

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col">
      <ServiceWorkerRegister />
      <header
        className="border-edge bg-bg/90 sticky top-0 z-40 flex items-center justify-between border-b px-4 py-3 backdrop-blur"
        style={{ paddingTop: "max(env(safe-area-inset-top), 0.75rem)" }}
      >
        <p className="font-display text-base font-semibold tracking-tight">
          Vantage<span className="text-amber">.</span>{" "}
          <span className="micro text-faint align-middle">DRIVER</span>
        </p>
        <div className="flex items-center gap-3">
          <span className="micro text-muted flex items-center gap-1.5">
            <span
              className="animate-pulse-dot bg-green inline-block size-1.5 rounded-full"
              aria-hidden
            />
            {me.user.full_name.split(" ")[0]}
          </span>
          <form action={signOutAction}>
            <button type="submit" className="micro text-faint hover:text-coral transition-colors">
              Exit
            </button>
          </form>
        </div>
      </header>

      <main className="flex-1 px-4 pt-4 pb-24">{children}</main>

      <TabBar />
    </div>
  );
}
