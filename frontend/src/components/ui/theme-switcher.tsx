"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { cx } from "@/lib/cx";
import { DEFAULT_THEME, THEMES, applyTheme, currentTheme } from "@/lib/themes";

/** Re-render whenever html[data-theme] changes (applyTheme mutates it). */
function subscribeThemeAttr(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

/**
 * Floating theme picker — demo/pitch affordance so a client can flip the
 * whole product between visual directions live. Renders nothing when only
 * one theme is registered.
 */
export function ThemeSwitcher() {
  const [open, setOpen] = useState(false);
  const active = useSyncExternalStore(subscribeThemeAttr, currentTheme, () => DEFAULT_THEME);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (THEMES.length < 2) return null;
  // Never on the driver PWA: the floating pill would sit on top of the
  // bottom tab bar. The pitch/demo audience is the advertiser/admin desktop.
  if (pathname?.startsWith("/driver")) return null;

  const activeMeta = THEMES.find((t) => t.slug === active);

  return (
    // hidden below lg: on small screens the pill overlaps page-bottom
    // actions (verified via Playwright pointer-interception traces).
    <div ref={rootRef} className="fixed right-4 bottom-4 z-50 hidden print:hidden lg:block">
      {open ? (
        <div className="border-edge-strong bg-panel shadow-panel animate-rise absolute right-0 bottom-14 w-72 rounded-xl border p-2">
          <p className="micro text-faint px-2 pt-1 pb-2">Visual direction</p>
          <ul role="listbox" aria-label="Visual direction" className="flex flex-col gap-1">
            {THEMES.map((t) => {
              const selected = t.slug === active;
              return (
                <li key={t.slug}>
                  <button
                    role="option"
                    aria-selected={selected}
                    onClick={() => applyTheme(t.slug)}
                    className={cx(
                      "flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors",
                      selected ? "bg-raised" : "hover:bg-raised/60",
                    )}
                  >
                    <span
                      aria-hidden
                      className="border-edge-strong flex shrink-0 overflow-hidden rounded-md border"
                    >
                      {t.swatches.map((c, i) => (
                        <span key={i} className="h-6 w-3" style={{ backgroundColor: c }} />
                      ))}
                    </span>
                    <span className="min-w-0">
                      <span className="text-ink block truncate text-sm font-medium">
                        {t.name}
                        {selected ? <span className="text-amber"> ·</span> : null}
                      </span>
                      {t.tagline ? (
                        <span className="text-muted block truncate text-xs">{t.tagline}</span>
                      ) : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="border-edge-strong bg-raised text-ink shadow-panel hover:border-amber/60 flex h-11 items-center gap-2.5 rounded-full border px-4 text-sm transition-colors"
      >
        <span aria-hidden className="flex overflow-hidden rounded-sm">
          {(activeMeta?.swatches ?? []).map((c, i) => (
            <span key={i} className="h-3.5 w-1.5" style={{ backgroundColor: c }} />
          ))}
        </span>
        <span className="max-w-36 truncate">{activeMeta?.name ?? "Theme"}</span>
      </button>
    </div>
  );
}
