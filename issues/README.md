# Cardvert audit corpus

This directory preserves the independent first-pass audits commissioned for
Cardvert on 1 September 2026 and the later product/UI prompt suite that has
been deliberately paused.

Raw audit responses are provenance records, not accepted repository truth.
Findings become actionable only after they are normalized, checked against the
current source, classified, ordered and independently reviewed.

## Layout

- `audit-manifest.md` — authoritative inventory and collection status.
- `audits/raw/` — one sanitized Markdown artifact per source response.
- `findings/` — current-source verification records created later.
- `planning/` — consolidation and remediation-order documents created later.
- `prompts/` — paused future audit prompts; these are not active work.

## Current boundary

The expected first-pass corpus contains 14 audit responses:

- 8 ChatGPT GPT-5.6 Pro conversations in or adjacent to the TSS project;
- 2 Codex audit tasks;
- 4 Claude Opus conversations, as confirmed by the project owner.

Older Claude future-delivery and external-dependency sessions are excluded from
this first-pass corpus. They remain discoverable in their original source and
are listed in the manifest so their exclusion is explicit.

Collection is closed: all 14 expected responses are represented by separate
raw artifacts, and all 14 are complete. There are no missing, incomplete or
duplicate first-pass responses.

The corrected consolidation is independently admitted at `master`
`38094d605830ccce111bcb0773ec1a249fed2d58`: 115 candidates and 131 source
mappings resolve into 86 executable fixes across 60 acyclic remediation slices,
plus separate deferred, owner-decision and external-input registers. The final
GPT-5.6 Pro review signed off with no required changes. The durable receipt is
`.codex/delivery/cardvert-audit-reconciliation/pro-admission-review.md`.

No product correction is authorized by this directory alone.
