import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { signOutAction } from "@/lib/auth/actions";
import { TabBar } from "@/components/driver/tab-bar";
import { ServiceWorkerRegister } from "@/components/driver/sw-register";

/**
 * Vantage Driver — an installable PWA, not a portal. Standalone app chrome:
 * slim top bar, content well, bottom tab bar. Advertiser/admin keep the
 * desktop shell; this surface is phone-first end to end.
 */

export const metadata: Metadata = {
  title: { default: "Vantage Driver", template: "%s · Vantage Driver" },
  manifest: "/driver/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Vantage Driver",
  },
  icons: {
    apple: "/icons/driver-180.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0b0e",
  width: "device-width",
  initialScale: 1,
  // App-like: the UI manages its own scroll surfaces
  viewportFit: "cover",
};

export default async function DriverLayout({ children }: { children: ReactNode }) {
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
