"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { CapabilitySnapshot } from "@/lib/pwa/capability-contract";
import { useCapabilityProbes } from "./use-capability-probes";

type Row = { label: string; ok: boolean; fix: string; passive?: boolean };

function rows(s: CapabilitySnapshot): Row[] {
  return [
    {
      label: "Cardvert is on your home screen",
      ok: s.secureContext && s.manifestLinked && s.displayMode === "standalone",
      fix: "Open your browser menu, choose Add to Home Screen, then open Cardvert from that icon.",
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
      label: "You're signed in",
      ok: s.session === "valid",
      fix: "Check your internet connection, then sign in again.",
    },
  ];
}

/** D38(b): the driver's plain Phone check; codes and the raw report stay on the support view. */
export function PhoneCheck() {
  const { snapshot, passiveReady, busy, report, checkAll } = useCapabilityProbes();
  const [checked, setChecked] = useState(false);
  const [copyNotice, setCopyNotice] = useState("");

  async function runCheck() {
    await checkAll();
    setChecked(true);
  }

  async function copyForSupport() {
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(report);
      setCopyNotice("Copied. Paste it into your message to support.");
    } catch {
      setCopyNotice("Couldn't copy on this phone. Ask support how to send the check result.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Phone check</h1>
        <p className="text-muted mt-2 text-sm leading-6">
          Checks that this phone can record your trips. Location is only asked for when you press
          the button.
        </p>
      </div>

      <Button
        type="button"
        onClick={() => void runCheck()}
        disabled={!passiveReady || busy !== null}
        className="h-12 w-full"
      >
        {busy ? "Checking…" : checked ? "Check again" : "Check this phone"}
      </Button>

      <ul aria-label="Phone check results" className="flex flex-col gap-2">
        {rows(snapshot).map((row) => {
          const known = checked || (row.passive && passiveReady);
          return (
            <li key={row.label} className="rounded border p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium">{row.label}</p>
                <p
                  className={
                    known
                      ? row.ok
                        ? "text-green text-sm"
                        : "text-coral text-sm"
                      : "text-muted text-sm"
                  }
                >
                  {known ? (row.ok ? "Yes" : "No") : "Not checked yet"}
                </p>
              </div>
              {known && !row.ok ? (
                <p className="text-muted mt-1 text-xs leading-5">{row.fix}</p>
              ) : null}
            </li>
          );
        })}
      </ul>

      <div>
        <button
          type="button"
          className="text-amber text-sm underline"
          onClick={() => void copyForSupport()}
        >
          Copy for support
        </button>
        <p role="status" aria-live="polite" className="text-muted mt-1 text-xs">
          {copyNotice}
        </p>
      </div>
    </div>
  );
}
