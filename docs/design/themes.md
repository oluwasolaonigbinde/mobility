# Visual directions

The client kept four switchable product designs (D37), and two new candidates
were added for review (REQ-071). The floating picker labels them Directions
1–6. The public Terrax landing page has its own namespaced styling and does not
take part in product theme selection.

| Direction | Name | Slug | Design language |
| --- | --- | --- | --- |
| 1 | Ivory Ledger | `ivory-ledger` | Warm paper, Fraunces display type, ruled panels, terracotta accents |
| 2 | Broadside | `broadside` | Poster typography, pill controls, bone canvas and forest navigation |
| 3 | Dispatch | `dispatch` | Deep forest navigation around a calm paper workspace, Poppins and gold |
| 4 | Ledger | `ledger` | Flat light surfaces, restrained rules, Archivo and deep teal |
| 5 | Route | `route` | The current public site: Poppins headlines, pill eyebrows and ink pill buttons, soft cards, gold dashed route line, crimson accent, light shell |
| 6 | Wrap | `wrap` | Vehicle-wrap blocks: wide clay shell, Archivo capitals at a larger scale, 2px ink outlines, hard offset shadows, square corners |

Menu labels in the desktop sidebar and the mobile menu are one size step above
other small labels in every direction (13px; Broadside 16px because its face is
condensed; Wrap 14px in Archivo).

Ivory Ledger is the default for first visits and for obsolete or invalid saved
theme choices. All six choices use `html[data-theme="<slug>"]` with CSS token
overrides in `frontend/src/app/globals.css`. The registry and pre-paint
localStorage bootstrap live in `frontend/src/lib/themes.ts`; registry tests
check that every choice has a token block and scoped design rules.

The full retained palette specifications and measured contrast pairs are in
[theme-specs.json](theme-specs.json). Product font binaries are self-hosted.
Maps use the configured provider style or a local schematic background; no
retained direction requires a separate basemap tint.
