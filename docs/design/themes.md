# Retained visual directions

The client selected four switchable product designs. The floating picker labels
them Directions 1–4. The public Terrax landing page has its own namespaced
styling and does not take part in product theme selection.

| Direction | Name | Slug | Design language |
| --- | --- | --- | --- |
| 1 | Ivory Ledger | `ivory-ledger` | Warm paper, Fraunces display type, ruled panels, terracotta accents |
| 2 | Broadside | `broadside` | Poster typography, pill controls, bone canvas and forest navigation |
| 3 | Dispatch | `dispatch` | Deep forest navigation around a calm paper workspace, Poppins and gold |
| 4 | Ledger | `ledger` | Flat light surfaces, restrained rules, Archivo and deep teal |

Ivory Ledger is the default for first visits and for obsolete or invalid saved
theme choices. All four choices use `html[data-theme="<slug>"]` with CSS token
overrides in `frontend/src/app/globals.css`. The registry and pre-paint
localStorage bootstrap live in `frontend/src/lib/themes.ts`; registry tests
check that every choice has a token block and scoped design rules.

The full retained palette specifications and measured contrast pairs are in
[theme-specs.json](theme-specs.json). Product font binaries are self-hosted.
Maps use the configured provider style or a local schematic background; no
retained direction requires a separate basemap tint.
