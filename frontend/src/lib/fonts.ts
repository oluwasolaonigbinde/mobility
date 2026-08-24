import localFont from "next/font/local";
import { Archivo, Bricolage_Grotesque, Fraunces, IBM_Plex_Mono, Inter } from "next/font/google";

/**
 * The Vantage type system, self-hosted (zero external font requests):
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
 * Delete the losers here and in globals.css once the client picks.
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

export const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const fraunces = Fraunces({
  subsets: ["latin"],
  axes: ["opsz"],
  variable: "--font-fraunces",
  display: "swap",
});

export const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  display: "swap",
});

export const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});
