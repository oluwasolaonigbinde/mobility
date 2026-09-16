"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MAILTO, NAV, ROUTES } from "@/lib/marketing/site";
import { Icon } from "./icon";
import { Wordmark } from "./wordmark";

/**
 * Sticky primary navigation.
 *
 * Below `lg` the links collapse into a disclosure panel. The panel is a real
 * disclosure, not a dialog: the button owns `aria-expanded` and `aria-controls`,
 * Escape closes it and returns focus to the button, choosing a link closes it,
 * and it is removed from the DOM when closed so its links are never reachable
 * by keyboard while hidden.
 */
export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, close]);

  return (
    <header className="border-terrax-ink/10 bg-terrax-paper/85 sticky top-0 z-50 border-b backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 md:px-8 lg:py-4">
        <a
          href="#top"
          className="flex min-w-0 items-center rounded-md"
          aria-label="Terrax Media — back to top"
        >
          <Wordmark variant="light" className="h-9 w-auto md:h-10" priority />
        </a>

        <nav aria-label="Primary" className="hidden items-center gap-8 lg:flex">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-terrax-ink-soft hover:text-terrax-ink rounded-sm text-sm font-medium transition-colors"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <a
            href={ROUTES.signIn}
            className="text-terrax-ink hover:bg-terrax-ink/5 hidden rounded-full px-4 py-2.5 text-sm font-semibold transition-colors sm:inline-flex"
          >
            Open Cardvert
          </a>
          <a
            href={MAILTO.campaign}
            className="bg-terrax-gold font-terrax-display text-terrax-ink hover:bg-terrax-crimson-ink hover:text-terrax-card hidden items-center gap-2 rounded-full px-5 py-2.5 text-sm font-extrabold transition-colors sm:inline-flex"
          >
            Start a Campaign
            <Icon name="arrowRight" className="size-4" />
          </a>

          <button
            ref={buttonRef}
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls="primary-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            className="border-terrax-ink/20 text-terrax-ink grid size-10 place-items-center rounded-full border lg:hidden"
          >
            <Icon name={open ? "close" : "menu"} className="size-5" />
          </button>
        </div>
      </div>

      {open ? (
        <nav
          id="primary-menu"
          aria-label="Primary"
          className="border-terrax-ink/10 bg-terrax-card border-t lg:hidden"
        >
          <ul className="mx-auto max-w-7xl px-5 py-3 md:px-8">
            {NAV.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="text-terrax-ink block rounded-md py-3 text-base font-medium"
                >
                  {item.label}
                </a>
              </li>
            ))}
            <li className="pt-2 pb-1 sm:hidden">
              <a
                href={ROUTES.signIn}
                onClick={() => setOpen(false)}
                className="border-terrax-ink/20 text-terrax-ink mr-2 inline-flex items-center rounded-full border px-5 py-2.5 text-sm font-semibold"
              >
                Open Cardvert
              </a>
              <a
                href={MAILTO.campaign}
                onClick={() => setOpen(false)}
                className="bg-terrax-gold font-terrax-display text-terrax-ink inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-extrabold"
              >
                Start a Campaign
                <Icon name="arrowRight" className="size-4" />
              </a>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
