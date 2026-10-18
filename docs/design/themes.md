# Cardvert brand look

D98 (18 October 2026, REQ-181/185) replaces the selectable visual directions
with one white and brand-green signed-in design. The registry, picker,
per-direction CSS and stored-choice bootstrap are removed.

- White surfaces and very dark green text (`#0a1c09`). Green actions use
  `#256f1a` with white text; danger and information retain readable colours.
- The official Terrax symbol sits beside Cardvert on advertiser/driver headers.
  Its original green-to-red gradient is preserved; it is not redrawn or recoloured.
- Advertiser and driver surfaces use Poppins headings, readable sans labels and
  soft cards. Admin gets palette changes only, with its type, control geometry,
  navigation and side panels retained.
- Public marketing keeps its namespaced palette and established styling.
- Tokens live in `frontend/src/app/globals.css`; there is no saved theme choice.

Phase 1 delivery and verification are recorded under REQ-181–186. Cancellation
request sending, real driver artwork and the live spending projection remain
Phase 2 integrations. Earlier visual directions are historical decisions, not
selectable application implementations.
