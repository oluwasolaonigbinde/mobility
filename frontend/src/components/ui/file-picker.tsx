"use client";

import { useEffect, useId, useRef, useState } from "react";
import { cx } from "@/lib/cx";

export type FilePickerState = "idle" | "uploading" | "uploaded" | "failed";

const stateText: Record<Exclude<FilePickerState, "idle">, string> = {
  uploading: "Uploading…",
  uploaded: "Uploaded",
  failed: "Upload failed",
};

/**
 * File input shown as a button with the chosen file's name or thumbnail, Replace and Remove.
 * The real input keeps its `name`, so forms that read FormData or `form.elements` still work,
 * and it clears with `form.reset()`.
 */
export function FilePicker({
  label,
  name,
  accept,
  capture,
  required,
  disabled,
  hint,
  state = "idle",
  error,
  onFile,
}: {
  label: string;
  name?: string;
  accept?: string;
  capture?: "environment" | "user";
  required?: boolean;
  disabled?: boolean;
  hint?: string;
  state?: FilePickerState;
  error?: string;
  onFile?: (file: File | undefined) => void;
}) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState<string>();

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form) return;
    const clear = () => {
      setFile(undefined);
      setPreview(undefined);
    };
    form.addEventListener("reset", clear);
    return () => form.removeEventListener("reset", clear);
  }, []);

  function remove() {
    if (inputRef.current) inputRef.current.value = "";
    setFile(undefined);
    setPreview(undefined);
    onFile?.(undefined);
  }

  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-ink text-sm font-medium">
        {label}
      </label>
      <input
        ref={inputRef}
        id={id}
        name={name}
        type="file"
        accept={accept}
        capture={capture}
        required={required}
        disabled={disabled}
        aria-describedby={describedBy || undefined}
        aria-invalid={error ? true : undefined}
        className="sr-only"
        onChange={(event) => {
          const next = event.currentTarget.files?.[0];
          setFile(next);
          setPreview(
            next?.type.startsWith("image/") && typeof URL.createObjectURL === "function"
              ? URL.createObjectURL(next)
              : undefined,
          );
          onFile?.(next);
        }}
      />
      <div
        className={cx(
          "bg-raised flex min-h-14 items-center gap-3 rounded-lg border px-3 py-2",
          error || state === "failed" ? "border-coral/60" : "border-edge",
        )}
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element -- local object URL preview
          <img src={preview} alt="" className="size-10 shrink-0 rounded object-cover" />
        ) : null}
        <div className="min-w-0 flex-1">
          {file ? (
            <p className="truncate text-sm" title={file.name}>
              {file.name}
            </p>
          ) : (
            <p className="text-faint text-sm">No file chosen</p>
          )}
          {state !== "idle" ? (
            <p
              className={cx(
                "text-xs",
                state === "failed"
                  ? "text-coral"
                  : state === "uploaded"
                    ? "text-green"
                    : "text-muted",
              )}
            >
              {stateText[state]}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="border-edge text-ink hover:border-edge-strong h-9 shrink-0 rounded-full border px-4 text-sm font-medium disabled:opacity-50"
        >
          {file ? "Replace" : capture ? "Take photo" : "Choose file"}
        </button>
        {file ? (
          <button
            type="button"
            disabled={disabled}
            onClick={remove}
            className="text-muted hover:text-coral h-9 shrink-0 px-2 text-sm disabled:opacity-50"
          >
            Remove
          </button>
        ) : null}
      </div>
      {hint ? (
        <p id={`${id}-hint`} className="text-muted text-xs">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
