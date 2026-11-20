"use client";

import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { cx } from "@/lib/cx";
import { feedbackNamePrefill } from "./actions";
import { captureViewport } from "./capture";

const NAME_MAX = 120;
const MESSAGE_MAX = 5000;
const PAGE_MAX = 500;

type Mark = { dataUrl: string; pinX: number; pinY: number; pagePath: string };
type Phase = "closed" | "open" | "marking" | "capturing" | "sending" | "sent";

/** Driver portal pages carry a bottom tab bar; sit above it there. */
function bottomOffset(pathname: string): string {
  const tabBar = pathname.startsWith("/driver") && !pathname.startsWith("/driver/change-password");
  return `calc(${tabBar ? "5rem" : "1rem"} + env(safe-area-inset-bottom))`;
}

function sendError(status: number): string {
  if (status === 429) return "You've sent a lot of feedback. Try again in a few minutes.";
  if (status === 413) return "That screenshot is too large. Remove the mark and try again.";
  return "Couldn't send your feedback. Try again.";
}

/** Site-wide "Feedback" button (REQ-336). Built only when NEXT_PUBLIC_FEEDBACK_ENABLED is 1. */
export function FeedbackWidget() {
  if (process.env.NEXT_PUBLIC_FEEDBACK_ENABLED !== "1") return null;
  return <FeedbackWidgetPanel />;
}

function FeedbackWidgetPanel() {
  const pathname = usePathname() || "/";
  const [phase, setPhase] = useState<Phase>("closed");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState("");
  const [mark, setMark] = useState<Mark | null>(null);
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; message?: string }>({});
  const [keyboard, setKeyboard] = useState<{ inset: number; height?: number }>({ inset: 0 });
  const prefilled = useRef(false);
  const nameTouched = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const firstField = useRef<HTMLInputElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const pagePath = pathname.slice(0, PAGE_MAX);

  const close = useCallback(() => {
    setPhase("closed");
    setError(undefined);
    requestAnimationFrame(() => trigger.current?.focus());
  }, []);

  function open() {
    setPhase("open");
    setError(undefined);
    if (!prefilled.current) {
      prefilled.current = true;
      feedbackNamePrefill()
        .then((value) => {
          if (value && !nameTouched.current) setName(value);
        })
        .catch(() => undefined);
    }
  }

  // Phones keep fixed elements behind the on-screen keyboard; lift the panel above it.
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () =>
      setKeyboard({
        inset: Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop),
        height: viewport.height,
      });
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
    };
  }, []);

  useEffect(() => {
    if (phase === "open") firstField.current?.focus();
    if (phase === "marking") overlay.current?.focus();
  }, [phase]);

  useEffect(() => {
    if (phase !== "open" && phase !== "marking" && phase !== "sent") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (phase === "marking") setPhase("open");
      else close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [phase, close]);

  async function markAt(clientX: number, clientY: number) {
    const pinX = Math.min(1, Math.max(0, clientX / window.innerWidth));
    const pinY = Math.min(1, Math.max(0, clientY / window.innerHeight));
    const markedPath = pagePath;
    setPhase("capturing");
    // Let the overlay and panel leave the screen before the capture starts.
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    try {
      const dataUrl = await captureViewport();
      setMark({ dataUrl, pinX, pinY, pagePath: markedPath });
      setNotice(undefined);
    } catch {
      setMark(null);
      setNotice("We couldn't capture the screen. You can still send your feedback without it.");
    }
    setPhase("open");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedMessage = message.trim();
    const errors = {
      name: trimmedName ? undefined : "Enter your name",
      message: trimmedMessage ? undefined : "Enter your feedback",
    };
    setFieldErrors(errors);
    if (errors.name || errors.message) return;
    setPhase("sending");
    setError(undefined);
    try {
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: trimmedName.slice(0, NAME_MAX),
          // A marked note belongs to the page the screenshot shows.
          page_path: mark?.pagePath ?? pagePath,
          message: trimmedMessage.slice(0, MESSAGE_MAX),
          website: website || null,
          screenshot: mark ? { data_url: mark.dataUrl, pin_x: mark.pinX, pin_y: mark.pinY } : null,
        }),
      });
      if (!response.ok) {
        setError(sendError(response.status));
        setPhase("open");
        return;
      }
      setMessage("");
      setMark(null);
      setNotice(undefined);
      setPhase("sent");
    } catch {
      setError(sendError(0));
      setPhase("open");
    }
  }

  if (pathname.startsWith("/feedback")) return null;
  const bottom = bottomOffset(pathname);
  const panelVisible = phase === "open" || phase === "sending" || phase === "sent";
  const keyboardOpen = keyboard.inset > 80;
  const panelBottom = keyboardOpen ? `${keyboard.inset + 8}px` : bottom;
  const panelMaxHeight =
    keyboardOpen && keyboard.height
      ? `${keyboard.height - 16}px`
      : `calc(100dvh - ${bottom} - 1rem)`;

  return (
    <div data-feedback-widget className="font-sans">
      {/* Lets the end of every page scroll clear of the floating button. */}
      <div aria-hidden="true" className="h-16 shrink-0" />
      {phase === "closed" ? (
        <button
          ref={trigger}
          type="button"
          onClick={open}
          aria-haspopup="dialog"
          className="bg-ink fixed right-4 z-40 inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium text-white shadow-lg transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ bottom }}
        >
          Feedback
        </button>
      ) : null}

      {phase === "marking" ? (
        <div
          ref={overlay}
          tabIndex={-1}
          role="application"
          aria-label="Tap or click the spot you want to mark. Press Escape to cancel."
          className="fixed inset-0 z-[60] cursor-crosshair bg-transparent outline-none"
          onClick={(event) => void markAt(event.clientX, event.clientY)}
        >
          <p className="bg-ink pointer-events-none fixed top-4 left-1/2 -translate-x-1/2 rounded-full px-4 py-2 text-sm text-white shadow-lg">
            Tap the spot you want to mark
          </p>
        </div>
      ) : null}

      {panelVisible ? (
        <div
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          className="border-edge bg-panel text-ink fixed right-4 z-40 w-[min(24rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border p-4 shadow-xl"
          style={{ bottom: panelBottom, maxHeight: panelMaxHeight }}
        >
          <h2 id={titleId} className="font-display text-lg font-semibold">
            Send feedback
          </h2>
          {phase === "sent" ? (
            <div className="mt-3 grid gap-3">
              <p role="status" className="text-green text-sm font-medium">
                Thanks — feedback sent
              </p>
              <Button type="button" variant="ghost" onClick={close}>
                Close
              </Button>
            </div>
          ) : (
            <form onSubmit={submit} noValidate className="mt-3 grid gap-3">
              <FeedbackField label="Your name" error={fieldErrors.name}>
                {(id, describedBy) => (
                  <input
                    ref={firstField}
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={fieldErrors.name ? true : undefined}
                    value={name}
                    maxLength={NAME_MAX}
                    required
                    autoComplete="name"
                    onChange={(event) => {
                      nameTouched.current = true;
                      setName(event.target.value);
                    }}
                    className={inputClass(Boolean(fieldErrors.name))}
                  />
                )}
              </FeedbackField>
              <FeedbackField label="Current page">
                {(id) => (
                  <input
                    id={id}
                    value={mark?.pagePath ?? pagePath}
                    readOnly
                    className="border-edge bg-raised text-muted h-10 rounded-lg border px-3 text-sm"
                  />
                )}
              </FeedbackField>
              <FeedbackField label="Feedback" error={fieldErrors.message}>
                {(id, describedBy) => (
                  <textarea
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={fieldErrors.message ? true : undefined}
                    value={message}
                    maxLength={MESSAGE_MAX}
                    required
                    rows={4}
                    onChange={(event) => setMessage(event.target.value)}
                    className={cx(inputClass(Boolean(fieldErrors.message)), "h-auto py-2")}
                  />
                )}
              </FeedbackField>
              <div
                aria-hidden="true"
                className="absolute -left-[10000px] h-px w-px overflow-hidden"
              >
                <label>
                  Website
                  <input
                    name="website"
                    tabIndex={-1}
                    autoComplete="off"
                    value={website}
                    onChange={(event) => setWebsite(event.target.value)}
                  />
                </label>
              </div>
              {mark ? (
                <div className="border-edge relative overflow-hidden rounded-lg border">
                  {/* eslint-disable-next-line @next/next/no-img-element -- local data URL preview */}
                  <img src={mark.dataUrl} alt="Marked screenshot" className="block w-full" />
                  <span
                    aria-hidden="true"
                    className="bg-coral absolute size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
                    style={{ left: `${mark.pinX * 100}%`, top: `${mark.pinY * 100}%` }}
                  />
                </div>
              ) : null}
              {notice ? (
                <p role="status" className="text-muted text-sm">
                  {notice}
                </p>
              ) : null}
              {error ? (
                <p role="alert" className="text-coral text-sm">
                  {error}
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  className="h-10 px-3"
                  disabled={phase === "sending"}
                  onClick={() => {
                    if (mark) setMark(null);
                    else {
                      setNotice(undefined);
                      setPhase("marking");
                    }
                  }}
                >
                  {mark ? "Remove mark" : "Mark area"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="h-10 px-3"
                  disabled={phase === "sending"}
                  onClick={close}
                >
                  Cancel
                </Button>
                <Button type="submit" className="h-10 flex-1 px-3" disabled={phase === "sending"}>
                  {phase === "sending" ? "Sending…" : "Send feedback"}
                </Button>
              </div>
            </form>
          )}
        </div>
      ) : null}

      {phase === "capturing" ? (
        // Inside the widget root, so the capture leaves it out; it blocks taps meanwhile.
        <div data-testid="feedback-capturing" className="fixed inset-0 z-[60] cursor-wait">
          <p
            role="status"
            className="bg-ink fixed top-4 left-1/2 -translate-x-1/2 rounded-full px-4 py-2 text-sm text-white shadow-lg"
          >
            Capturing the screen…
          </p>
        </div>
      ) : null}
    </div>
  );
}

function inputClass(invalid: boolean) {
  return cx(
    "bg-raised text-ink h-10 rounded-lg border px-3 text-sm focus:border-amber focus:outline-none",
    invalid ? "border-coral/60" : "border-edge",
  );
}

function FeedbackField({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: (id: string, describedBy?: string) => React.ReactNode;
}) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children(id, error ? errorId : undefined)}
      {error ? (
        <p id={errorId} className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
