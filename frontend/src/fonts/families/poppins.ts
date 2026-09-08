import localFont from "next/font/local";

/**
 * Poppins — vendored from Google Fonts, self-hosted, no build-time or runtime
 * network access. The binaries, their exact upstream URLs, sha256 hashes and the
 * SIL OFL 1.1 licence are recorded in `../google/provenance.json`.
 *
 * next/font/local applies `declarations` to every `src` entry, so each Google
 * subset needs its own call to keep its own `unicode-range`. The ranges are
 * disjoint, so glyph routing is decided by `unicode-range`, not chain order.
 * Only the terminal latin face carries the metric-adjusted fallback (Arial),
 * so the range-less fallback @font-face stays last in the chain and never
 * shadows an earlier subset.
 * Only latin is preloaded, matching the previous `subsets: ["latin"]`.
 */
const poppinsDevanagari = localFont({
  src: [
    { path: "../google/Poppins-400-devanagari.woff2", weight: "400", style: "normal" },
    { path: "../google/Poppins-500-devanagari.woff2", weight: "500", style: "normal" },
    { path: "../google/Poppins-600-devanagari.woff2", weight: "600", style: "normal" },
    { path: "../google/Poppins-800-devanagari.woff2", weight: "800", style: "normal" },
  ],
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0900-097F, U+1CD0-1CF9, U+200C-200D, U+20A8, U+20B9, U+20F0, U+25CC, U+A830-A839, U+A8E0-A8FF, U+11B00-11B09" },
  ],
});

const poppinsLatinExt = localFont({
  src: [
    { path: "../google/Poppins-400-latin-ext.woff2", weight: "400", style: "normal" },
    { path: "../google/Poppins-500-latin-ext.woff2", weight: "500", style: "normal" },
    { path: "../google/Poppins-600-latin-ext.woff2", weight: "600", style: "normal" },
    { path: "../google/Poppins-800-latin-ext.woff2", weight: "800", style: "normal" },
  ],
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF" },
  ],
});

const poppinsLatin = localFont({
  src: [
    { path: "../google/Poppins-400-latin.woff2", weight: "400", style: "normal" },
    { path: "../google/Poppins-500-latin.woff2", weight: "500", style: "normal" },
    { path: "../google/Poppins-600-latin.woff2", weight: "600", style: "normal" },
    { path: "../google/Poppins-800-latin.woff2", weight: "800", style: "normal" },
  ],
  display: "swap",
  adjustFontFallback: "Arial",
  declarations: [
    { prop: "unicode-range", value: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  ],
});

/** Font-family chain for the `Poppins` faces, in Google's own subset order. */
export const poppins = [poppinsDevanagari, poppinsLatinExt, poppinsLatin]
  .map((face) => face.style.fontFamily)
  .join(", ");
