"use client";

import { Button } from "@/components/ui/button";
import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";

export function SensitiveReview({
  purpose,
  children,
}: {
  purpose: string;
  children: ReactNode | ((show: () => void) => ReactNode);
}) {
  const [open, setOpen] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [readAttempt, setReadAttempt] = useState(0);
  const hide = useCallback(() => {
    setOpen(false);
    setGeneration((value) => value + 1);
  }, []);
  const show = () => {
    setOpen(true);
    setReadAttempt((value) => value + 1);
  };
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
    <div className="min-w-0" onSubmitCapture={typeof children === "function" ? undefined : show}>
      <p className="text-faint text-xs">Purpose: {purpose}</p>
      {open ? (
        <button
          type="button"
          className="text-cyan mt-1 min-h-11 min-w-11 text-xs underline md:min-h-0 md:min-w-0"
          onClick={hide}
        >
          Hide
        </button>
      ) : null}
      <Fragment key={generation}>
        {typeof children === "function" ? children(show) : children}
      </Fragment>
    </div>
  );
}

type DocumentReadResult = { downloadUrl?: string; error?: string };

export function ReviewDocument({
  read,
  onOpened,
  showFallback,
}: {
  read: () => Promise<DocumentReadResult>;
  onOpened: () => void;
  showFallback: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<DocumentReadResult>({});
  const currentRead = useRef<AbortController | null>(null);
  useEffect(() => () => currentRead.current?.abort(), []);

  async function open() {
    const tab = window.open("", "_blank");
    if (tab) tab.opener = null;
    else showFallback();

    const controller = new AbortController();
    currentRead.current = controller;
    controller.signal.addEventListener("abort", () => tab?.close(), { once: true });
    setPending(true);
    setResult({});
    try {
      const { downloadUrl, error } = await read();
      if (controller.signal.aborted) return;
      if (!downloadUrl) {
        tab?.close();
        setResult({ error: error ?? "This document could not be opened. Try again." });
      } else if (tab && !tab.closed) {
        tab.location.replace(downloadUrl);
        onOpened();
      } else {
        if (tab) showFallback();
        setResult({ downloadUrl });
      }
    } catch {
      if (controller.signal.aborted) return;
      tab?.close();
      setResult({ error: "This document could not be opened. Try again." });
    } finally {
      if (!controller.signal.aborted) {
        currentRead.current = null;
        setPending(false);
      }
    }
  }

  return (
    <div className="border-edge rounded-lg border p-2">
      {result.downloadUrl ? (
        <a
          href={result.downloadUrl}
          target="_blank"
          rel="noopener noreferrer"
          data-feedback-private
          className="text-cyan inline-flex min-h-11 items-center text-xs underline md:min-h-8"
          onClick={onOpened}
        >
          Open document
        </a>
      ) : (
        <Button
          type="button"
          disabled={pending}
          variant="ghost"
          className="h-11 px-2 text-xs md:h-8"
          onClick={() => void open()}
        >
          {pending ? "Opening…" : "Open document"}
        </Button>
      )}
      {result.error ? (
        <p role="alert" className="text-coral mt-1 text-xs">
          {result.error}
        </p>
      ) : null}
    </div>
  );
}
