import { plexMono } from "@/fonts/families/ibm-plex-mono";
import { poppins } from "@/fonts/families/poppins";

/**
 * Poppins is the Terrax Media brand face ("Clean, sans-serif font (Poppins)
 * throughout" — Brand Guide §4/§5). It carries display and body here, but set
 * lowercase and very tight rather than as blocks of ExtraBold caps.
 *
 * IBM Plex Mono is added for micro-labels, numerals and tags only. It is not a
 * second brand voice; it is the "route manifest" texture that gives the page
 * its editorial rhythm, and it never sets a headline or a paragraph.
 *
 * The landing page keeps its own variables so it never depends on the
 * switchable product type system in `src/lib/fonts.ts`; it shares only the
 * vendored binaries, so importing these families adds no extra font payload.
 */
export const landingFontVariables = {
  "--tx-font": poppins,
  "--tx-mono": plexMono,
} as React.CSSProperties;
