import type { CapabilitySnapshot } from "./capability-contract";

export type ReadinessRow = { label: string; ok: boolean; fix: string; passive?: boolean };

/**
 * D38(b): the driver's plain view of the capability snapshot. Every condition that
 * `assessPilotPwa` needs before Start is covered by exactly one row, so a blocked Start always
 * has at least one failing row to show.
 */
export function readinessRows(s: CapabilitySnapshot): ReadinessRow[] {
  return [
    {
      label: "Cardvert is on your home screen",
      ok:
        s.secureContext &&
        s.manifestLinked &&
        s.serviceWorker === "registered" &&
        s.displayMode === "standalone",
      fix: "Open your browser menu, choose Add to Home Screen, then open Cardvert from that icon.",
      passive: true,
    },
    {
      label: "Cardvert is open on screen",
      ok: s.visibility === "visible",
      fix: "Keep Cardvert open on the screen while you start and drive.",
      passive: true,
    },
    {
      label: "Location is allowed",
      ok: s.location === "granted",
      fix: "Allow location for Cardvert in your phone settings, then check again.",
    },
    {
      label: "The screen can stay on",
      ok: s.wakeLock === "pass",
      fix: "Update your browser, or use Chrome on Android or Safari on iPhone.",
    },
    {
      label: "Trips can be saved on this phone",
      ok: s.indexedDb === "pass" && s.durableQueue === "pass" && s.webLocks === "pass",
      fix: "Close other Cardvert tabs, make sure the phone has free storage and isn't in private browsing.",
    },
    {
      label: "You're online",
      ok: s.online,
      fix: "Turn on mobile data or Wi-Fi, then try again.",
      passive: true,
    },
    {
      label: "You're signed in",
      ok: s.session === "valid",
      fix: "Check your internet connection, then sign in again.",
    },
  ];
}
