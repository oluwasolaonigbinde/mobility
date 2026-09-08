import localFont from "next/font/local";

import { archivo } from "@/fonts/families/archivo";
import { bigShoulders } from "@/fonts/families/big-shoulders";
import { bricolage } from "@/fonts/families/bricolage-grotesque";
import { fraunces } from "@/fonts/families/fraunces";
import { inter } from "@/fonts/families/inter";
import { plexMono } from "@/fonts/families/ibm-plex-mono";
import { poppins } from "@/fonts/families/poppins";

/**
 * The Cardvert type system, self-hosted (zero external font requests, at build
 * time as well as in the browser):
 * - Clash Display — headlines, KPI numerals ("the voice")
 * - Satoshi — UI text and body copy
 * - IBM Plex Mono — data, labels, telemetry
 *
 * Candidate-theme voices (each visual direction carries its own display
 * face; the theme blocks in globals.css remap --font-display/--font-sans):
 * - Inter — Daylight Ops (precision-instrument SaaS)
 * - Fraunces — Ivory Ledger (editorial serif / banknote engraving)
 * - Bricolage Grotesque — Danfo (characterful, hand-painted-adjacent)
 * - Archivo (wdth axis) — Hi-Vis (expanded industrial/DIN)
 * - Poppins — Terra Grain (the Terrax Media brand typeface; used for display
 *   AND body, per the brand guide's "Poppins throughout" rule)
 * - Big Shoulders + Inter — Broadside (the pairing used by the Terrax landing
 *   page; Google has since merged Display/Text into one family with an `opsz`
 *   axis, so one variable face covers both roles)
 * Delete the losers here and in globals.css once the client picks.
 *
 * The formerly Google-hosted families are vendored under `src/fonts/google` and
 * declared per family in `src/fonts/families`, which export font-family chains
 * rather than font objects; the root layout assigns them to the CSS variables
 * below. See `src/fonts/google/provenance.json` for asset and licence detail.
 */

export const clashDisplay = localFont({
  src: [
    { path: "../fonts/ClashDisplay-500.woff2", weight: "500", style: "normal" },
    { path: "../fonts/ClashDisplay-600.woff2", weight: "600", style: "normal" },
    { path: "../fonts/ClashDisplay-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-clash",
  display: "swap",
});

export const satoshi = localFont({
  src: [
    { path: "../fonts/Satoshi-400.woff2", weight: "400", style: "normal" },
    { path: "../fonts/Satoshi-500.woff2", weight: "500", style: "normal" },
    { path: "../fonts/Satoshi-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-satoshi",
  display: "swap",
});

/** CSS custom properties for the vendored families, set on the root element. */
export const productFontVariables = {
  "--font-plex-mono": plexMono,
  "--font-inter": inter,
  "--font-fraunces": fraunces,
  "--font-bricolage": bricolage,
  "--font-archivo": archivo,
  "--font-poppins": poppins,
  "--font-big-shoulders": bigShoulders,
} as React.CSSProperties;
