"use client";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";

export function HubDrawer({
  title,
  closeHref,
  children,
}: {
  title: string;
  closeHref: string;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const headingId = useId();
  const router = useRouter();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    closeButton.current?.focus();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  const close = () => router.push(closeHref, { scroll: false });
  return (
    <dialog
      ref={dialog}
      aria-labelledby={headingId}
      className="border-edge bg-panel text-ink backdrop:bg-bg/70 fixed inset-y-0 right-0 left-auto z-50 m-0 h-dvh max-h-dvh w-full max-w-2xl overflow-y-auto border-l p-4 shadow-2xl md:p-6"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <div className="mb-5 flex items-start justify-between gap-3">
        <h2 id={headingId} className="font-display text-xl font-semibold">
          {title}
        </h2>
        <button
          ref={closeButton}
          onClick={close}
          className="border-edge rounded-lg border px-3 py-2 text-sm"
        >
          Close
        </button>
      </div>
      {children}
    </dialog>
  );
}
