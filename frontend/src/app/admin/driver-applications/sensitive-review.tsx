"use client";

import { useEffect, useState, type ReactNode } from "react";

export function SensitiveReview({ purpose, children }: { purpose: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    if (!open) return;
    const hide = () => setOpen(false);
    const timer = window.setTimeout(hide, 60_000);
    const visibility = () => {
      if (document.visibilityState !== "visible") hide();
    };
    window.addEventListener("pagehide", hide);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pagehide", hide);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [open]);
  return (
    <div className="border-edge rounded-lg border p-2">
      {open ? (
        <>
          <button
            type="button"
            className="text-cyan mb-2 text-xs underline"
            onClick={() => setOpen(false)}
          >
            Hide protected evidence
          </button>
          {children}
        </>
      ) : (
        <>
          <label className="text-muted flex flex-col gap-1 text-xs">
            Review purpose
            <select
              value={selected ? purpose : ""}
              onChange={(e) => setSelected(e.target.value === purpose)}
              className="border-edge bg-raised text-ink rounded border p-2"
            >
              <option value="">Select purpose…</option>
              <option value={purpose}>{purpose}</option>
            </select>
          </label>
          <label className="text-muted my-2 flex items-start gap-2 text-xs">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />{" "}
            I need this current evidence for the selected review.
          </label>
          <button
            type="button"
            className="text-cyan text-xs underline disabled:opacity-50"
            disabled={!selected || !confirmed}
            onClick={() => setOpen(true)}
          >
            Confirm and open protected review
          </button>
        </>
      )}
    </div>
  );
}
