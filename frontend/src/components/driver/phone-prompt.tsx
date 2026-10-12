"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";

export function PhonePrompt({ driverId }: { driverId: string }) {
  const [dismissed, setDismissed] = useState(false);
  const key = `cardvert-phone-intro:${driverId}`;
  const visible = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return localStorage.getItem(key) !== "seen";
      } catch {
        return true;
      }
    },
    () => false,
  );
  if (!visible || dismissed) return null;
  return (
    <Panel className="p-4" aria-label="Phone setup">
      <p className="text-sm">Add Cardvert to your Home Screen and keep it open while driving.</p>
      <div className="mt-3 flex items-center justify-between gap-3">
        <Link href="/driver/capabilities" className="text-amber text-sm">
          Check this phone
        </Link>
        <button
          type="button"
          className="text-sm font-medium"
          onClick={() => {
            try {
              localStorage.setItem(key, "seen");
            } catch {}
            setDismissed(true);
          }}
        >
          Got it
        </button>
      </div>
    </Panel>
  );
}

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}
