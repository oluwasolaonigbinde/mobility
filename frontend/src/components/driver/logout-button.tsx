"use client";

import { signOutAction } from "@/lib/auth/actions";

export const DRIVER_SESSION_CHANNEL = "cardvert-driver-session";

export function notifyDriverLogout(): void {
  window.dispatchEvent(new Event("cardvert-driver-logout"));
  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel(DRIVER_SESSION_CHANNEL);
    channel.postMessage({ type: "logout" });
    channel.close();
  }
}

export function DriverLogoutButton() {
  return (
    <form action={signOutAction} onSubmit={notifyDriverLogout}>
      <button type="submit" className="micro text-faint hover:text-coral transition-colors">
        Exit
      </button>
    </form>
  );
}
