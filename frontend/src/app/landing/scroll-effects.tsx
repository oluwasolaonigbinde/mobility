"use client";

import { useEffect } from "react";

/**
 * Scroll behaviour for the landing page. Renders nothing.
 *
 * 1. Deep links. Arriving at `/landing#contact` must land on that section.
 *    The browser's own anchor jump is cancelled during hydration (it stops a
 *    few pixels down the page), so the hash is applied once here, instantly.
 * 2. Smooth scrolling is enabled only after that, via `data-tx-ready`, so the
 *    fix above is not itself animated away.
 * 3. Reveals. Any `[data-tx-reveal]` element is marked visible as it enters
 *    the viewport. Under `prefers-reduced-motion: reduce` everything is marked
 *    visible immediately, and the hidden state is gated behind
 *    `@media (scripting: enabled)` so a no-JS render shows the whole page.
 */
export function ScrollEffects() {
  useEffect(() => {
    const root = document.documentElement;

    if (window.location.hash) {
      // `querySelector` throws on a syntactically invalid hash from the URL bar.
      try {
        document.querySelector(window.location.hash)?.scrollIntoView();
      } catch {
        /* not a valid selector — leave the page where it is */
      }
    }
    root.dataset.txReady = "";

    const targets = Array.from(document.querySelectorAll<HTMLElement>("[data-tx-reveal]"));
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduced) {
      targets.forEach((el) => (el.dataset.visible = "true"));
      return () => {
        delete root.dataset.txReady;
      };
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          (entry.target as HTMLElement).dataset.visible = "true";
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );

    targets.forEach((el) => observer.observe(el));
    return () => {
      observer.disconnect();
      delete root.dataset.txReady;
    };
  }, []);

  return null;
}
