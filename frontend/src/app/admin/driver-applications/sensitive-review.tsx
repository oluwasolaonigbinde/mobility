"use client";

import { Fragment, useCallback, useEffect, useState, type ReactNode } from "react";

export function SensitiveReview({ purpose, children }: { purpose: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [readAttempt, setReadAttempt] = useState(0);
  const hide = useCallback(() => {
    setOpen(false);
    setGeneration((value) => value + 1);
  }, []);
  useEffect(() => {
    if (!open) return;
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
  }, [open, readAttempt, hide]);
  return (
    <div
      className="min-w-0"
      onSubmitCapture={() => {
        setOpen(true);
        setReadAttempt((value) => value + 1);
      }}
    >
      <p className="text-faint text-xs">Purpose: {purpose}</p>
      {open ? (
        <button type="button" className="text-cyan mt-1 text-xs underline" onClick={hide}>
          Hide
        </button>
      ) : null}
      <Fragment key={generation}>{children}</Fragment>
    </div>
  );
}
