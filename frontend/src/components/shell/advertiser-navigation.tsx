"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { SidebarNav } from "./sidebar-nav";
import { BrandWordmark } from "./brand-wordmark";
import { PortalIcon } from "@/components/brand/portal-icon";

const items = [
  { href: "/advertiser", label: "Home", exact: true, icon: <PortalIcon name="home" /> },
  { href: "/advertiser/campaigns", label: "Campaigns", icon: <PortalIcon name="megaphone" /> },
  { href: "/advertiser/reports", label: "Reports", icon: <PortalIcon name="chart" /> },
  { href: "/advertiser/billing", label: "Billing", icon: <PortalIcon name="bill" /> },
  { href: "/advertiser/help", label: "Help", icon: <PortalIcon name="help" /> },
  { href: "/advertiser/account", label: "Account", icon: <PortalIcon name="user" /> },
];

export function AdvertiserNavigation({ account }: { account: ReactNode }) {
  const pathname = usePathname();
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const desktop = useRef<HTMLElement>(null);
  const previousOverflow = useRef<string | null>(null);
  const close = () => dialog.current?.close();
  useEffect(() => {
    dialog.current?.close();
  }, [pathname]);
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 768px)");
    const resize = () => {
      if (wide.matches) dialog.current?.close();
    };
    wide.addEventListener("change", resize);
    return () => {
      wide.removeEventListener("change", resize);
      if (previousOverflow.current !== null)
        document.body.style.overflow = previousOverflow.current;
    };
  }, []);
  const list = (
    <div className="brand-nav flex min-h-0 flex-1 flex-col gap-6">
      <SidebarNav items={items} />
      <div className="border-edge mt-auto border-t px-4 pt-5">{account}</div>
    </div>
  );
  return (
    <>
      <aside
        ref={desktop}
        className="portal-sidebar border-edge hidden w-64 shrink-0 border-r md:block"
      >
        <div className="sticky top-0 flex h-dvh flex-col">
          <Link href="/advertiser" className="px-8 pt-8 pb-10">
            <BrandWordmark />
          </Link>
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 pb-6">{list}</div>
        </div>
      </aside>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="dialog"
        aria-controls="advertiser-menu"
        aria-label="Open menu"
        className="border-edge fixed top-3 left-4 z-50 flex h-11 w-11 items-center justify-center rounded-full border bg-white md:hidden"
        onClick={() => {
          if (dialog.current?.open) return;
          previousOverflow.current = document.body.style.overflow;
          dialog.current?.showModal();
          closeButton.current?.focus();
          document.body.style.overflow = "hidden";
        }}
      >
        <svg
          viewBox="0 0 24 24"
          className="size-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          aria-hidden="true"
        >
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <dialog
        ref={dialog}
        id="advertiser-menu"
        aria-label="Menu"
        className="advertiser-portal text-ink fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-[min(21rem,88vw)] max-w-none border-0 bg-white p-0 shadow-2xl backdrop:bg-black/35"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const controls = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
            ),
          ).filter((element) => element.getClientRects().length > 0);
          const first = closeButton.current;
          const last = controls.at(-1);
          if (event.shiftKey && document.activeElement === first && last) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last && first) {
            event.preventDefault();
            first.focus();
          }
        }}
        onClose={() => {
          if (previousOverflow.current !== null)
            document.body.style.overflow = previousOverflow.current;
          previousOverflow.current = null;
          if (window.matchMedia("(min-width: 768px)").matches)
            desktop.current?.querySelector<HTMLAnchorElement>("a[aria-current='page']")?.focus();
          else trigger.current?.focus();
        }}
        onClick={(event) => {
          if (event.target === dialog.current || (event.target as HTMLElement).closest("a,form"))
            close();
        }}
      >
        <div className="flex h-full flex-col px-5 pt-5 pb-6">
          <div className="mb-7 flex items-center justify-between">
            <p className="font-display text-xl font-semibold">Your Cardvert</p>
            <button
              ref={closeButton}
              type="button"
              aria-label="Close menu"
              className="brand-secondary size-11 p-0"
              onClick={close}
            >
              ×
            </button>
          </div>
          {list}
        </div>
      </dialog>
    </>
  );
}
