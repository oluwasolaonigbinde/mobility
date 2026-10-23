import type { ReactNode } from "react";

const paths = {
  home: <path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z" />,
  megaphone: (
    <>
      <path d="M3 10h4l11-5v14L7 14H3ZM7 14l2 7h4l-3-6M21 8v8" />
    </>
  ),
  wallet: (
    <>
      <path d="M4 7h16v14H4V5l13-2v4M16 12h5v5h-5Z" />
      <path d="M18 14.5h.01" />
    </>
  ),
  car: (
    <>
      <path d="m5 10 2-6h10l2 6M3 10h18v8H3ZM5 18v3M19 18v3M6 14h2M16 14h2" />
    </>
  ),
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  pin: (
    <>
      <path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 2v6M16 2v6" />
    </>
  ),
  bill: (
    <>
      <path d="M6 3h12v18l-3-2-3 2-3-2-3 2ZM9 8h6M9 12h6" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17v.1" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="7" r="4" />
      <path d="M4 22v-3a8 8 0 0 1 16 0v3" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  qr: (
    <>
      <path d="M3 3h6v6H3ZM15 3h6v6h-6ZM3 15h6v6H3ZM15 15h3v3h3v3h-6ZM21 12v3M12 3v3M12 12h3M3 12h3M12 18v3" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type PortalIconName = keyof typeof paths;
export function PortalIcon({
  name,
  className = "size-5",
}: {
  name: PortalIconName;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export function IconTile({
  name,
  tone = "green",
}: {
  name: PortalIconName;
  tone?: "green" | "gold" | "coral";
}) {
  return (
    <span className={`portal-icon-tile portal-icon-${tone}`}>
      <PortalIcon name={name} className="size-6" />
    </span>
  );
}
