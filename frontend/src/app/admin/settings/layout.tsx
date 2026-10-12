import type { ReactNode } from "react";
import { SettingsNav } from "./settings-nav";
export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <SettingsNav />
      {children}
    </>
  );
}
