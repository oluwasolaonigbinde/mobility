import type { Metadata } from "next";
import { plexMono, poppins } from "./fonts";
import { TAGLINE, WHO_WE_ARE } from "./content";
import "./terrax.css";

export const metadata: Metadata = {
  title: {
    absolute: `Terrax Media — ${TAGLINE}`,
  },
  description: `${WHO_WE_ARE} Moving vehicle advertising for brands, and a new income stream for approved drivers.`,
};

/**
 * The landing page is a public marketing surface, deliberately isolated from
 * the product shell: its own type system (Poppins), its own token set
 * (terrax.css) and no dependency on the switchable product themes.
 */
export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return <div className={`${poppins.variable} ${plexMono.variable} tx-page`}>{children}</div>;
}
