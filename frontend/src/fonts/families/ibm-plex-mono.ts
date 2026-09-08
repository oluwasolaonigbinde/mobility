import localFont from "next/font/local";

/**
 * IBM Plex Mono — vendored from Google Fonts, self-hosted, no build-time or runtime
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
const plexMonoCyrillicExt = localFont({
  src: [
    { path: "../google/IBMPlexMono-400-cyrillic-ext.woff2", weight: "400", style: "normal" },
    { path: "../google/IBMPlexMono-500-cyrillic-ext.woff2", weight: "500", style: "normal" },
    { path: "../google/IBMPlexMono-600-cyrillic-ext.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F" },
  ],
});

const plexMonoCyrillic = localFont({
  src: [
    { path: "../google/IBMPlexMono-400-cyrillic.woff2", weight: "400", style: "normal" },
    { path: "../google/IBMPlexMono-500-cyrillic.woff2", weight: "500", style: "normal" },
    { path: "../google/IBMPlexMono-600-cyrillic.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116" },
  ],
});

const plexMonoVietnamese = localFont({
  src: [
    { path: "../google/IBMPlexMono-400-vietnamese.woff2", weight: "400", style: "normal" },
    { path: "../google/IBMPlexMono-500-vietnamese.woff2", weight: "500", style: "normal" },
    { path: "../google/IBMPlexMono-600-vietnamese.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0102-0103, U+0110-0111, U+0128-0129, U+0168-0169, U+01A0-01A1, U+01AF-01B0, U+0300-0301, U+0303-0304, U+0308-0309, U+0323, U+0329, U+1EA0-1EF9, U+20AB" },
  ],
});

const plexMonoLatinExt = localFont({
  src: [
    { path: "../google/IBMPlexMono-400-latin-ext.woff2", weight: "400", style: "normal" },
    { path: "../google/IBMPlexMono-500-latin-ext.woff2", weight: "500", style: "normal" },
    { path: "../google/IBMPlexMono-600-latin-ext.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "unicode-range", value: "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF" },
  ],
});

const plexMonoLatin = localFont({
  src: [
    { path: "../google/IBMPlexMono-400-latin.woff2", weight: "400", style: "normal" },
    { path: "../google/IBMPlexMono-500-latin.woff2", weight: "500", style: "normal" },
    { path: "../google/IBMPlexMono-600-latin.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  adjustFontFallback: "Arial",
  declarations: [
    { prop: "unicode-range", value: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  ],
});

/** Font-family chain for the `IBM Plex Mono` faces, in Google's own subset order. */
export const plexMono = [plexMonoCyrillicExt, plexMonoCyrillic, plexMonoVietnamese, plexMonoLatinExt, plexMonoLatin]
  .map((face) => face.style.fontFamily)
  .join(", ");
