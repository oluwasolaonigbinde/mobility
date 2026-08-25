import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

/**
 * Cardvert Driver — an installable PWA, not a portal. Standalone app chrome:
 * slim top bar, content well, bottom tab bar. Advertiser/admin keep the
 * desktop shell; this surface is phone-first end to end.
 */

export const metadata: Metadata = {
  title: { default: "Cardvert Driver", template: "%s · Cardvert Driver" },
  manifest: "/driver/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Cardvert Driver",
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

export default function DriverLayout({ children }: { children: ReactNode }) {
  return children;
}
