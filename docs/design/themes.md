# Visual direction candidates

Client feedback on the 30 Jul demo: the product worked end-to-end but the UI read as
"all black." Response: candidate design languages implemented as live, switchable
themes — the client flips the real product (floating pill, bottom-right) and picks one.
Directions 1–6 came from that round. Directions 7–9 were added 25–26 Aug 2026:
Terra Grain and Coverage from the Terrax Media brand book, and Broadside from the
working Terrax landing page.

Each direction was designed, adversarially reviewed (WCAG-computed accessibility audit +
design critique), and reconciled. Full corrected token specs with contrast math:
[theme-specs.json](theme-specs.json).

## How it works

- Every theme is a CSS custom-property override block in
  `frontend/src/app/globals.css`, keyed to `html[data-theme="<slug>"]`. Components
  never branch on theme — they wear token classes and the variables re-map underneath.
- Beyond color, each theme carries its own design language: display typeface
  (`--font-display`), shape (`--radius-panel`), texture, motion, and signature
  elements (scoped rules in the unlayered section at the bottom of globals.css).
- Registry + persistence: `frontend/src/lib/themes.ts` (localStorage +
  pre-paint boot script in the root layout — no flash).
- Charts read `--chart-grid` / `--chart-tick` / `--chart-area-alpha` with sensible
  fallbacks; maps resolve light/dark basemap from the theme's `color-scheme`
  (`activeMapStyleUrl`), and Blue Hour retints basemap fills navy at load
  (`applyThemeMapTint`).

## The directions

Each direction is grounded in the product's own world (Lagos mobility, money,
routes, tarmac) — not just a palette:

| Theme | Slug | Language |
| --- | --- | --- |
| Daylight Ops | `daylight-ops` | Precision instrument: Inter, blueprint grid, panel rules drawn as transit route lines with terminus dots, cobalt on white |
| Ivory Ledger | `ivory-ledger` | Naira paper: Fraunces serif, guilloché security-print lattice, paper grain, ledger rules, terracotta on ivory |
| Blue Hour | `blue-hour` | Adire night: indigo-navy (never black) carrying an adire-eleko dot/dash pattern, glass panels, streetlight gold, drifting aurora |
| Danfo | `danfo` | Lagos transit livery: Bricolage Grotesque, yellow-and-black livery band, yellow sidebar with black coachline, tilted cabin-sticker chips, enamel painted buttons (vivid `#f7c400` is surface-only; ochre `#7d6300` carries accent text) |
| Hi-Vis | `hi-vis` | Fleet industrial: Archivo expanded, zero radius, 2px ink borders, hard offset shadows, hazard stripe, road centre-line under titles, number-plate ID chips, safety orange |
| Terra Grain | `terra-grain` | The Terrax Media brand book worn by the product: Poppins ExtraBold, "Rainforest Nights" #071e03 ground, the mark's wood grain as canvas texture, panels as the logo's rounded screen frame with its inner keyline, the logo gradient (green → brown → crimson) as the sidebar route rail, Golden Accent on every signal, Battle Cat green as surface-only |
| Coverage | `coverage` | The product's 500m × 500m reporting cell as the layout system: a real mint lattice on the canvas, flat square map cells with zero elevation, Battle Cat survey crop ticks on opposite corners, chips as legend keys with a leading tone bar, IBM Plex Mono headings (no new face loaded) |
| Broadside | `broadside` | The Terrax landing page turned into an application: Big Shoulders poster caps at 900/0.94, bone canvas with cards a step darker, 100px pill controls with 1.5px rules and an ink-filled CTA, the brand gradient growing as a nav underline, and the site's inverted forest band becoming the shell's navigation |

The original dark theme remains the default (`night` — no data attribute).

## Directions 7 and 8 · brand sources

Both are built from `docs/brand/terrax-media/`, not from a mood board.

### Direction 7 · Terra Grain

Every major choice traces to a document:

| Brand fact (source) | How it lands in the UI |
| --- | --- |
| Palette: Battle Cat `#256f1a`, Rainforest Nights `#071e03`, Crimson Flame `#ee2f41`, Golden Accent `#f2c94c`, Mint Whisper `#c8f6d0` (Brand Guide, "Colors") | Rainforest Nights is the ground, Golden Accent the interactive signal, Mint Whisper the telemetry voice; Battle Cat is a surface only (nav-active, route rail), never text |
| "Primary green (#266F1A) remains constant"; logotype colour `#0a1c09` (Brand Guide, marketing rules + logo construction) | The whole surface ramp is the Battle Cat / Rainforest Nights hue family, so the brand green is structural rather than decorative |
| Typeface: Poppins ExtraBold (Brand Guide, "Fonts") | `--font-display` and `--font-sans` are both Poppins; display sits at weight 800, block-set like the TERRAX MEDIA logotype |
| Symbol: a stylised "T" in a rounded rectangle over wood grain, which the guide reads as "creativity, organic growth, grounded storytelling" | The grain runs across the canvas and the sidebar as the product's own version of that idea: the trace a fleet leaves on the ground it covers |
| Frame: rounded rectangle with an inner keyline (the mark), and the business is screens mounted on vehicles (Brand Guide, "Who we are") | Every panel and chip is that frame — rounded, with a light inset keyline |
| Logo gradient: green `#256f1a` → brown `#7a5230` → red `#ee2f41` (Brand Guide, logo construction) | Runs down the sidebar — and along the mobile nav's bottom edge — as origin → road → destination |
| Taglines "Taking Your Message Further, Faster" / "Transforming City Movement into Brand Impact" (Tagline PDF) | Under `prefers-reduced-motion: no-preference` one mint highlight travels that rail — a single vehicle moving, which is what the product watches |
| Safe space: clear space of size `x` around the logo; never rotate, skew, recolour or filter (Brand Guide, safe space + prohibited use) | The supplied symbol ships unmodified and sits on a white plate with clear space on all four sides; `background-size` pins width only, so the 773:618 ratio cannot be distorted |

### Direction 8 · Coverage

Same palette source, different organising idea — the product's own unit of account
rather than the logo:

| Source | How it lands in the UI |
| --- | --- |
| "Each square is a 500m × 500m area" (the exposure heatmap's own copy) | A real 28px lattice on the canvas and the navigation band; panels are cells sitting on it |
| Coverage plots mark the squares they sampled | Battle Cat crop ticks on two opposite corners of every panel |
| A plan view has no depth (Brand Guide: limited decorative elements, borders as the visual cue) | `--shadow-panel` and all glow tokens are `none`; separation comes from hairlines and the lattice |
| Map legends key colour to meaning | Chips drop the pill for a square with a 3px bar of their own tone on the leading edge |
| Battle Cat is the constant primary (Brand Guide, marketing rules) | It is both the coverage colour and the interactive accent — 6.2:1 on panel, white on it at 6.2:1 |
| A measurement product should speak in the data's type | `--font-display` is IBM Plex Mono, already in the stack, so no new face is loaded |

## Direction 9 · Broadside — landing-page sources

Direction 9 is adapted from the working Terrax landing page rather than the brand
book. Its design language, not its content:

| Landing-page move | How it lands in the UI |
| --- | --- |
| `Big Shoulders Display` at 900, uppercase, `line-height: 0.94` | h1–h3 take the same poster treatment; values keep sentence-height so descenders and currency suffixes survive |
| `.btn` — 100px radius, 1.5px rule, uppercase letterspaced, `.btn-primary` filled with `--ink` | Every button is that pill; the primary action is ink-filled, not accent-filled |
| `nav.links a::after` — the 135° brand gradient growing from width 0 on hover | The same gradient under each nav item, `scaleX(0)` → `scaleX(1)` on hover and for the current page |
| Inverted `--forest` bands carrying a radial dot field | An app has no sections to alternate, so the band becomes the shell: navigation is forest with the dot field, content is bone |
| `--canvas` / `--canvas-2` (cards a step *darker* than the page) | Kept, which is what separates this from the other light directions |
| `outline: 2px solid var(--clay); outline-offset: 3px` | The same focus ring |
| A global `prefers-reduced-motion` kill switch | Hover lift and underline growth live inside `@media (prefers-reduced-motion: no-preference)` |

Colours are deepened only where the site's own values fail as text on a card:
clay `#b4463f` is 4.1:1 on `#e4e2cf`, so `#9c352f` holds the accent slot while pure
clay stays in the gradient and the focus ring, neither of which carries type.

## Known plumbing limit (pre-existing, all directions)

Tailwind v4 inlines `@theme` shadow literals into the generated `shadow-panel`
and `shadow-glow-amber` utilities, so **every** theme's override of
`--shadow-panel` / `--shadow-glow-*` is inert — directions 1–6 all render the
default `night` elevation. The tokens stay declared as each theme's intent.
Terra Grain paints its panel keyline and gold button glow with scoped rules in
the unlayered section of `globals.css` instead. Fixing the shared plumbing would
change how all six existing directions look, so it is deliberately left out of
the Direction 7 change.

## Locking in the winner

1. In `globals.css`: move the winning block's declarations into `@theme` / `:root`
   defaults, delete the other blocks and their signature sections.
2. In `themes.ts`: delete the losing entries (a single-entry registry hides the
   switcher automatically) — or delete the switcher + registry outright.
   `frontend/src/lib/themes.test.ts` asserts registry ↔ stylesheet parity, so it
   fails loudly if an entry outlives its token block.
3. In `fonts.ts` / `layout.tsx`: drop the unused faces. If Terra Grain does not
   win, also delete `frontend/public/themes/terra-grain/`.
4. Keep the winner's chart/map notes from `theme-specs.json` in mind for any new
   components (chip tint recipes, on-accent text pairing, status-color discipline).
