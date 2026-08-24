# Visual direction candidates

Client feedback on the 30 Jul demo: the product worked end-to-end but the UI read as
"all black." Response: five candidate design languages implemented as live, switchable
themes — the client flips the real product (floating pill, bottom-right) and picks one.

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

## The five directions

Each direction is grounded in the product's own world (Lagos mobility, money,
routes, tarmac) — not just a palette:

| Theme | Slug | Language |
| --- | --- | --- |
| Daylight Ops | `daylight-ops` | Precision instrument: Inter, blueprint grid, panel rules drawn as transit route lines with terminus dots, cobalt on white |
| Ivory Ledger | `ivory-ledger` | Naira paper: Fraunces serif, guilloché security-print lattice, paper grain, ledger rules, terracotta on ivory |
| Blue Hour | `blue-hour` | Adire night: indigo-navy (never black) carrying an adire-eleko dot/dash pattern, glass panels, streetlight gold, drifting aurora |
| Danfo | `danfo` | Lagos transit livery: Bricolage Grotesque, yellow-and-black livery band, yellow sidebar with black coachline, tilted cabin-sticker chips, enamel painted buttons (vivid `#f7c400` is surface-only; ochre `#7d6300` carries accent text) |
| Hi-Vis | `hi-vis` | Fleet industrial: Archivo expanded, zero radius, 2px ink borders, hard offset shadows, hazard stripe, road centre-line under titles, number-plate ID chips, safety orange |

The original dark theme remains the default (`night` — no data attribute).

## Locking in the winner

1. In `globals.css`: move the winning block's declarations into `@theme` / `:root`
   defaults, delete the other four blocks and their signature sections.
2. In `themes.ts`: delete the losing entries (a single-entry registry hides the
   switcher automatically) — or delete the switcher + registry outright.
3. In `fonts.ts` / `layout.tsx`: drop the unused faces.
4. Keep the winner's chart/map notes from `theme-specs.json` in mind for any new
   components (chip tint recipes, on-accent text pairing, status-color discipline).
