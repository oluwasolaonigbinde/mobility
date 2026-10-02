import Link from "next/link";
import type { ReactNode } from "react";
export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <nav aria-label="Settings" className="mb-6 flex flex-wrap gap-3 text-sm">
        {[
          ["staff", "Staff logins"],
          ["reach", "Reach estimates"],
          ["audiences", "Retargeting audiences"],
          ["activity", "Activity log"],
          ["support-tools", "Support tools"],
        ].map(([path, label]) => (
          <Link
            key={path}
            className="border-edge rounded-lg border px-3 py-2"
            href={`/admin/settings/${path}`}
          >
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </>
  );
}
