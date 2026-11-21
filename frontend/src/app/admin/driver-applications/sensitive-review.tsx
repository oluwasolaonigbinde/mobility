"use client";

import { Button } from "@/components/ui/button";
import {
  createContext,
  Fragment,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

const DocumentReview = createContext<{
  registerRead: (controller: AbortController) => () => void;
  setError: (error: string | null) => void;
} | null>(null);

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
  const [error, setError] = useState<string | null>(null);
  const activeDocumentRead = useRef<AbortController | null>(null);
  useEffect(() => () => activeDocumentRead.current?.abort(), []);
  const registerRead = useCallback((controller: AbortController) => {
    activeDocumentRead.current?.abort();
    activeDocumentRead.current = controller;
    return () => {
      if (activeDocumentRead.current === controller) activeDocumentRead.current = null;
    };
  }, []);
  const hide = useCallback(() => {
    setOpen(false);
    setError(null);
    setGeneration((value) => value + 1);
  }, []);
  const cancelAndHide = useCallback(() => {
    activeDocumentRead.current?.abort();
    hide();
  }, [hide]);
  const show = () => {
    setOpen(true);
    setReadAttempt((value) => value + 1);
  };
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(cancelAndHide, 60_000);
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
  }, [open, readAttempt, hide, cancelAndHide]);
  return (
    <div className="min-w-0" onSubmitCapture={typeof children === "function" ? undefined : show}>
      <p className="text-faint text-xs">Purpose: {purpose}</p>
      {open ? (
        <button
          type="button"
          className="text-cyan mt-1 min-h-11 min-w-11 text-xs underline md:min-h-0 md:min-w-0"
          onClick={cancelAndHide}
        >
          Hide
        </button>
      ) : null}
      <DocumentReview.Provider value={{ registerRead, setError }}>
        <Fragment key={generation}>
          {typeof children === "function" ? children(show) : children}
        </Fragment>
      </DocumentReview.Provider>
      {error ? (
        <p role="alert" className="text-coral mt-1 text-xs">
          {error}
        </p>
      ) : null}
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
  const [downloadUrl, setDownloadUrl] = useState<string>();
  const currentRead = useRef<AbortController | null>(null);
  const review = useContext(DocumentReview);
  useEffect(() => () => currentRead.current?.abort(), []);

  async function open() {
    const tab = window.open("", "_blank");
    if (tab) tab.opener = null;
    else showFallback();

    const controller = new AbortController();
    currentRead.current = controller;
    // The tab can take focus and reset this view before the signed URL arrives.
    const navigation = tab && review ? new AbortController() : controller;
    const unregister = review?.registerRead(navigation);
    navigation.signal.addEventListener("abort", () => tab?.close(), { once: true });
    setPending(true);
    setDownloadUrl(undefined);
    review?.setError(null);
    try {
      const { downloadUrl, error } = await read();
      if (navigation.signal.aborted) return;
      if (!downloadUrl) {
        tab?.close();
        review?.setError(error ?? "This document could not be opened. Try again.");
      } else if (tab && !tab.closed) {
        tab.location.replace(downloadUrl);
        onOpened();
      } else if (!controller.signal.aborted) {
        if (tab) showFallback();
        setDownloadUrl(downloadUrl);
      }
    } catch {
      if (navigation.signal.aborted) return;
      tab?.close();
      review?.setError("This document could not be opened. Try again.");
    } finally {
      unregister?.();
      if (!controller.signal.aborted) {
        currentRead.current = null;
        setPending(false);
      }
    }
  }

  return (
    <div className="border-edge rounded-lg border p-2">
      {downloadUrl ? (
        <a
          href={downloadUrl}
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
    </div>
  );
}
