"use client";
import { useEffect, useRef, useState, useTransition } from "react";
import Image from "next/image";
import {
  searchOperatorOptions,
  previewOperatorArtwork,
  type SelectionKind,
  type SelectionOption,
} from "./queue-options";

export function SearchSelect({
  kind,
  name,
  label,
  parentId,
  value,
  onSelect,
}: {
  kind: SelectionKind;
  name: string;
  label: string;
  parentId?: string;
  value?: string;
  onSelect?: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<SelectionOption>();
  const [result, setResult] = useState<{
    items: SelectionOption[];
    total: number;
    error?: string;
  }>();
  const [offset, setOffset] = useState(0);
  const [pending, start] = useTransition();
  const [preview, setPreview] = useState<{ url?: string; error?: string }>();
  useEffect(() => {
    if (!preview?.url) return;
    const timer = window.setTimeout(() => setPreview(undefined), 60_000);
    return () => window.clearTimeout(timer);
  }, [preview]);
  const request = useRef(0);
  function search(nextOffset: number) {
    const id = ++request.current;
    start(async () => {
      const next = await searchOperatorOptions({ kind, q, offset: nextOffset, parentId });
      if (request.current === id) {
        setResult(next);
        setOffset(nextOffset);
      }
    });
  }
  return (
    <fieldset className="border-edge min-w-0 rounded-lg border p-3">
      <legend className="text-muted px-1 text-sm">{label}</legend>
      <input type="hidden" name={name} value={value ?? selected?.id ?? ""} />
      {selected ? (
        <p className="text-green mb-2 text-sm">
          Selected: {selected.label} · {selected.detail}
        </p>
      ) : null}
      {selected?.fileId ? (
        <button
          type="button"
          className="text-cyan mb-2 text-sm underline"
          disabled={pending}
          onClick={() =>
            start(async () => setPreview(await previewOperatorArtwork(selected.fileId!)))
          }
        >
          Preview selected artwork
        </button>
      ) : null}
      {preview?.url ? (
        <Image
          src={preview.url}
          alt="Selected campaign artwork"
          width={320}
          height={240}
          unoptimized
          className="max-w-full rounded object-contain"
        />
      ) : null}
      {preview?.error ? <p role="alert">{preview.error}</p> : null}
      <div className="flex flex-wrap gap-2">
        {kind !== "creative" ? (
          <input
            aria-label={`Search ${label}`}
            maxLength={120}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="border-edge bg-raised min-w-0 flex-1 rounded border p-2"
          />
        ) : null}
        <button
          type="button"
          disabled={pending}
          onClick={() => search(0)}
          className="text-cyan p-2 text-sm"
        >
          {pending ? "Loading…" : `Find ${label.toLowerCase()}`}
        </button>
      </div>
      {result?.error ? (
        <p role="alert" className="text-coral text-sm">
          {result.error}
        </p>
      ) : result ? (
        <>
          <p className="text-muted my-2 text-xs">
            {result.total} results · Final eligibility is rechecked when you submit.
          </p>
          <ul className="space-y-2">
            {result.items.map((option) => (
              <li key={option.id}>
                <button
                  type="button"
                  disabled={!!option.unavailable}
                  onClick={() => {
                    setSelected(option);
                    setPreview(undefined);
                    onSelect?.(option.id);
                  }}
                  className="border-edge w-full rounded border p-2 text-left disabled:opacity-60"
                >
                  <span className="block text-sm">{option.label}</span>
                  <span className="text-muted block text-xs break-all">{option.detail}</span>
                  {option.unavailable ? (
                    <span className="text-coral text-xs">{option.unavailable}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex gap-4">
            <button
              type="button"
              disabled={pending || offset === 0}
              onClick={() => search(Math.max(0, offset - 25))}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={pending || offset + 25 >= result.total}
              onClick={() => search(offset + 25)}
            >
              Next
            </button>
          </div>
        </>
      ) : null}
    </fieldset>
  );
}
