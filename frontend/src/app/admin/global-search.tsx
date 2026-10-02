"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { searchAdmin, type SearchGroup } from "./global-search-actions";

export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<SearchGroup[]>();
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let current = true;
    if (q.trim().length < 2) return;
    const timer = window.setTimeout(() => {
      setLoading(true);
      searchAdmin(q)
        .then((groups) => {
          if (current) {
            setResult(groups);
            setError(false);
          }
        })
        .catch(() => {
          if (current) setError(true);
        })
        .finally(() => {
          if (current) setLoading(false);
        });
    }, 300);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [q]);
  useEffect(() => {
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  return (
    <div
      ref={root}
      className="relative w-full max-w-xl"
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <label className="sr-only" htmlFor="admin-search">
        Search drivers, cars, campaigns, companies
      </label>
      <input
        id="admin-search"
        type="search"
        autoComplete="off"
        value={q}
        maxLength={120}
        placeholder="Search drivers, cars, campaigns, companies"
        aria-controls="admin-search-results"
        className="border-edge bg-raised h-10 w-full min-w-0 rounded-lg border px-3 text-sm"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setResult(undefined);
          setError(false);
          setLoading(false);
          setOpen(true);
        }}
      />
      {open && q.trim().length >= 2 ? (
        <div
          id="admin-search-results"
          className="border-edge bg-panel absolute top-full z-50 mt-2 max-h-[70dvh] w-full overflow-y-auto rounded-xl border p-3 shadow-xl"
          aria-live="polite"
        >
          {loading || (!result && !error) ? (
            <p className="text-muted p-2 text-sm">Searching…</p>
          ) : null}
          {error ? <p role="alert">Couldn&apos;t load this section — try again</p> : null}
          {result?.map((group) => (
            <section key={group.name} className="mb-3">
              <h2 className="micro text-muted px-2">{group.name}</h2>
              {group.unavailable ? (
                <p role="alert" className="px-2 text-sm">
                  Couldn&apos;t load this section — try again
                </p>
              ) : null}
              {!group.items.length && !group.unavailable ? (
                <p className="text-faint px-2 text-sm">No matches</p>
              ) : null}
              {group.items.map((hit) => (
                <Link
                  key={hit.href}
                  href={hit.href}
                  onClick={() => setOpen(false)}
                  className="hover:bg-raised focus:bg-raised block rounded-lg p-2 text-sm"
                >
                  <span className="block font-medium">{hit.name}</span>
                  <span className="text-muted block text-xs break-words">{hit.detail}</span>
                </Link>
              ))}
            </section>
          ))}
        </div>
      ) : null}
    </div>
  );
}
