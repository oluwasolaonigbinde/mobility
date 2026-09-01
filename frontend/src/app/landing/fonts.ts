import { IBM_Plex_Mono, Poppins } from "next/font/google";

/**
 * Poppins is the Terrax Media brand face ("Clean, sans-serif font (Poppins)
 * throughout" — Brand Guide §4/§5). It carries display and body here, but set
 * lowercase and very tight rather than as blocks of ExtraBold caps.
 *
 * IBM Plex Mono is added for micro-labels, numerals and tags only. It is not a
 * second brand voice; it is the "route manifest" texture that gives the page
 * its editorial rhythm, and it never sets a headline or a paragraph.
 *
 * Declared locally so the landing page never touches the shared product type
 * system in `src/lib/fonts.ts`.
 */
export const poppins = Poppins({
  weight: ["400", "500", "600", "800"],
  subsets: ["latin"],
  variable: "--tx-font",
  display: "swap",
});

export const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--tx-mono",
  display: "swap",
});
