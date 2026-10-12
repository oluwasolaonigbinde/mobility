"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { readinessRows } from "@/lib/pwa/readiness-rows";
import { useCapabilityProbes } from "./use-capability-probes";

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
        {readinessRows(snapshot).map((row) => {
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
