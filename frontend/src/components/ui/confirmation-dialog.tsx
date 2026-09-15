"use client";

import { type ReactNode, type RefObject, useEffect, useId, useRef } from "react";
import { Button } from "./button";

export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  cancelLabel,
  confirmLabel,
  onConfirm,
  returnFocusRef,
  pending = false,
  error,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  cancelLabel: string;
  confirmLabel: string;
  onConfirm: () => void;
  returnFocusRef: RefObject<HTMLElement | null>;
  pending?: boolean;
  error?: string;
  children?: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const wasOpenRef = useRef(false);
  const titleId = useId();
  const descriptionId = useId();

  function close() {
    const dialog = dialogRef.current;
    if (dialog?.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
    onOpenChange(false);
    queueMicrotask(() => returnFocusRef.current?.focus());
  }

  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && dialog && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      dialog.querySelector<HTMLButtonElement>("[data-dialog-cancel]")?.focus();
    } else if (!open && wasOpenRef.current) {
      queueMicrotask(() => returnFocusRef.current?.focus());
    }
    wasOpenRef.current = open;
  }, [open, returnFocusRef]);

  if (!open) return null;

  return (
    <dialog
      ref={dialogRef}
      role="alertdialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      className="border-coral/40 bg-panel text-ink backdrop:bg-bg/80 fixed inset-0 z-50 m-auto w-[calc(100%-2rem)] max-w-sm rounded-xl border p-5 shadow-xl backdrop:backdrop-blur-sm"
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) close();
      }}
      onKeyDown={(event) => {
        if (event.key === "Tab") {
          const focusable = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
            ),
          );
          const first = focusable[0];
          const last = focusable.at(-1);
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }
        if (event.key === "Escape") {
          event.preventDefault();
          if (!pending) close();
        }
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm();
        }}
      >
        <h2 id={titleId} className="font-display text-lg font-semibold">
          {title}
        </h2>
        <p id={descriptionId} className="text-muted mt-2 text-sm">
          {description}
        </p>
        {children ? <div className="mt-4">{children}</div> : null}
        {error ? (
          <p role="alert" className="text-coral mt-3 text-xs">
            {error}
          </p>
        ) : null}
        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            data-dialog-cancel
            type="button"
            variant="ghost"
            disabled={pending}
            onClick={close}
          >
            {cancelLabel}
          </Button>
          <Button type="submit" variant="danger" disabled={pending}>
            {pending ? "Working…" : confirmLabel}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
