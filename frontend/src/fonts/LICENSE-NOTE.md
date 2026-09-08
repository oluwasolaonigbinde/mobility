# Vendored fonts

Every face the product renders is self-hosted. Nothing is fetched from a font
CDN at build time or in the browser.

- **Clash Display** and **Satoshi** — Indian Type Foundry, distributed via
  [Fontshare](https://www.fontshare.com) under the ITF Free Font License
  (free for personal and commercial use; self-hosting permitted). Declared in
  `src/lib/fonts.ts`.
- **Inter, Fraunces, Bricolage Grotesque, Archivo, Poppins, Big Shoulders** and
  **IBM Plex Mono** — vendored from Google Fonts under the SIL Open Font License
  1.1. The binaries live in `google/`, one file per family/weight/subset, and
  are declared per family in `families/*.ts`. Each family's licence is
  kept verbatim in `google/licenses/OFL-<Family>.txt`, and
  `google/provenance.json` records every file's family, subset, weight,
  unicode-range, exact upstream `fonts.gstatic.com` URL and sha256.

`src/fonts/vendored-fonts.test.ts` fails if a `next/font/google` import returns,
if a vendored binary stops matching its recorded hash or licence, or if a
retained font variable is dropped from a layout.

If the client later licenses a different brand typeface, swap it in
`src/lib/fonts.ts` — nothing else references the Clash Display or Satoshi files
directly.
