import localFont from "next/font/local";
import { IBM_Plex_Mono } from "next/font/google";

/**
 * The Vantage type system, self-hosted (zero external font requests):
 * - Clash Display — headlines, KPI numerals ("the voice")
 * - Satoshi — UI text and body copy
 * - IBM Plex Mono — data, labels, telemetry
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
