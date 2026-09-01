"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Image from "next/image";
import { MAILTO, NAV } from "./content";

/**
 * Sticky brand header with a mobile disclosure menu.
 *
 * Behaviours: shadow/border on scroll, Escape closes, focus returns to the
 * toggle, background scroll is locked while open, and the menu closes when a
 * link is followed or the viewport grows past the desktop breakpoint.
 */
export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const menuId = useId();
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const close = useCallback(({ refocus }: { refocus?: boolean } = {}) => {
    setOpen(false);
    if (refocus) toggleRef.current?.focus();
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close({ refocus: true });
    };
    // The desktop nav takes over past this width; leaving the panel mounted
    // would trap focus in a hidden element.
    const wide = window.matchMedia("(min-width: 900px)");
    const onWide = () => wide.matches && close();

    document.addEventListener("keydown", onKeyDown);
    wide.addEventListener("change", onWide);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    menuRef.current?.querySelector<HTMLElement>("a, button")?.focus();

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      wide.removeEventListener("change", onWide);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, close]);

  return (
    <header className="tx-header" data-scrolled={scrolled}>
      <div className="tx-shell tx-header__bar">
        <a
          href="#tx-main"
          className="tx-logo"
          style={{ ["--tx-logo-h" as string]: "30px" }}
          aria-label="Terrax Media — back to top"
        >
          {/* Full-colour lockup — the approved form on a light ground. */}
          <Image
            src="/brand/terrax/terrax-logo.png"
            alt="Terrax Media"
            width={2092}
            height={680}
            sizes="160px"
            priority
          />
        </a>

        <nav className="tx-header__nav" aria-label="Primary">
          {NAV.map((item) => (
            <a key={item.href} className="tx-header__link" href={item.href}>
              {item.label}
            </a>
          ))}
        </nav>

        <div className="tx-header__actions">
          <a className="tx-btn tx-btn--ink tx-header__cta" href={MAILTO.campaign}>
            Start a campaign
          </a>
          <button
            ref={toggleRef}
            type="button"
            className="tx-burger"
            aria-expanded={open}
            aria-controls={menuId}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </div>

      {open ? (
        <div className="tx-menu" id={menuId} ref={menuRef}>
          <nav aria-label="Primary, mobile">
            <ul className="tx-menu__list">
              {NAV.map((item) => (
                <li key={item.href}>
                  <a href={item.href} onClick={() => close()}>
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="tx-menu__actions">
            <a className="tx-btn tx-btn--ink" href={MAILTO.campaign} onClick={() => close()}>
              Start a campaign
            </a>
            <a className="tx-btn tx-btn--outline" href={MAILTO.driver} onClick={() => close()}>
              Earn as a driver
            </a>
          </div>
        </div>
      ) : null}
    </header>
  );
}
