import { archivo } from "@/fonts/families/archivo";
import { bigShoulders } from "@/fonts/families/big-shoulders";
import { fraunces } from "@/fonts/families/fraunces";
import { inter } from "@/fonts/families/inter";
import { plexMono } from "@/fonts/families/ibm-plex-mono";
import { poppins } from "@/fonts/families/poppins";

/**
 * The Cardvert type system, self-hosted (zero external font requests, at build
 * time as well as in the browser):
 * - Fraunces — available display face; staff screens use Inter
 * - Inter — UI text and body copy
 * - IBM Plex Mono — available data face; staff labels use Inter
 * - Poppins — advertiser/driver headings and the public Terrax site
 *
 * The additional vendored families retain their provenance and licences;
 * there are no selectable product directions or font-provider requests.
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
