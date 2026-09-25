import { archivo } from "@/fonts/families/archivo";
import { bigShoulders } from "@/fonts/families/big-shoulders";
import { fraunces } from "@/fonts/families/fraunces";
import { inter } from "@/fonts/families/inter";
import { plexMono } from "@/fonts/families/ibm-plex-mono";
import { poppins } from "@/fonts/families/poppins";

/**
 * The Cardvert type system, self-hosted (zero external font requests, at build
 * time as well as in the browser):
 * - Fraunces — default display face
 * - Inter — UI text and body copy
 * - IBM Plex Mono — data, labels, telemetry
 *
 * Retained direction voices (the theme blocks remap --font-display/--font-sans):
 * - Fraunces — Ivory Ledger
 * - Poppins — Dispatch and the public Terrax site
 * - Archivo — Ledger
 * - Big Shoulders + Inter — Broadside
 * - Big Shoulders + Inter — Broadside (the pairing used by the Terrax landing
 *   page; Google has since merged Display/Text into one family with an `opsz`
 *   axis, so one variable face covers both roles)
 *
 * The formerly Google-hosted families are vendored under `src/fonts/google` and
 * declared per family in `src/fonts/families`, which export font-family chains
 * rather than font objects; the root layout assigns them to the CSS variables
 * below. See `src/fonts/google/provenance.json` for asset and licence detail.
 */

/** CSS custom properties for the vendored families, set on the root element. */
export const productFontVariables = {
  "--font-plex-mono": plexMono,
  "--font-inter": inter,
  "--font-fraunces": fraunces,
  "--font-archivo": archivo,
  "--font-poppins": poppins,
  "--font-big-shoulders": bigShoulders,
} as React.CSSProperties;
