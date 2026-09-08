import localFont from "next/font/local";

/**
 * Big Shoulders — vendored from Google Fonts, self-hosted, no build-time or runtime
 * network access. The binaries, their exact upstream URLs, sha256 hashes and the
 * SIL OFL 1.1 licence are recorded in `../google/provenance.json`.
 *
 * next/font/local applies `declarations` to every `src` entry, so each Google
 * subset needs its own call to keep its own `unicode-range`. The ranges are
 * disjoint, so glyph routing is decided by `unicode-range`, not chain order.
 * No metric-adjusted fallback face is generated: next/font/google emits none for
 * Big Shoulders (its metrics table has no entry for this family), so none is added here.
 * Only latin is preloaded, matching the previous `subsets: ["latin"]`.
 */
const bigShouldersVietnamese = localFont({
  src: [
    { path: "../google/BigShoulders-vietnamese.woff2" },
  ],
  weight: "100 900",
  style: "normal",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0102-0103, U+0110-0111, U+0128-0129, U+0168-0169, U+01A0-01A1, U+01AF-01B0, U+0300-0301, U+0303-0304, U+0308-0309, U+0323, U+0329, U+1EA0-1EF9, U+20AB" },
  ],
});

const bigShouldersLatinExt = localFont({
  src: [
    { path: "../google/BigShoulders-latin-ext.woff2" },
  ],
  weight: "100 900",
  style: "normal",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF" },
  ],
});

const bigShouldersLatin = localFont({
  src: [
    { path: "../google/BigShoulders-latin.woff2" },
  ],
  weight: "100 900",
  style: "normal",
  display: "swap",
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  ],
});

/** Font-family chain for the `Big Shoulders` faces, in Google's own subset order. */
export const bigShoulders = [bigShouldersVietnamese, bigShouldersLatinExt, bigShouldersLatin]
  .map((face) => face.style.fontFamily)
  .join(", ");
