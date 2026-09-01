# Mobility repository delivery instructions

This file is the single active repository-wide instruction source. Global
`AGENTS.md` supplies universal coding policy; this file supplies only Mobility's
delivery authority, queue, and repository gates; the nearest nested `AGENTS.md`
may add stronger directory-specific rules. A selected delivery skill owns the
execution lifecycle and must apply all of those instructions without restating
or weakening them.

## Required reading

Before planning or editing, the active controller reads these sources in order:

1. `docs/progress.md` — operational delivery control and sole work queue.
2. `docs/architecture.md` §1, §30, §35, plus sections referenced by the active
   package or checkpoint — design, placement, remediation, and gates.
3. `docs/decisions-log.md` — adopted product decisions and divergence guards.
4. This root `AGENTS.md`.
5. The nearest nested `AGENTS.md` for the files being changed, such as
   `frontend/AGENTS.md`.

A delegated worker reads only the exact excerpts, local rules, and source files
named in its bounded packet. The controller alone reads and edits the complete
programme ledger and `docs/progress.md`.

## Delivery authority and execution lock

- Implement only the package marked `NEXT`, `IN PROGRESS`, or `REVIEW` in the
  **Executable package queue**. There is exactly one active package. Inside it,
  implement only a runnable `TODO` selected by the package plan; the top
  `Current checkpoint` is a non-authorizing pointer.
- The 71 checklist items are acceptance obligations, not separate approvals or
  review cycles. The 22 `PARENT` rows are traceability only.
- `docs/next-steps.md`, architecture §31, old chats, TODOs, and
  `docs/build-loop/**` are context or historical evidence, not authority.
- A direct owner request outside the queue must be recorded in
  `docs/progress.md` before editing. It does not move the active package unless
  the owner explicitly reprioritizes the queue.
- Do not skip or reorder work silently. At promotion, use the dependency-safe
  scan and external-block rules defined in `docs/progress.md`; never invent an
  external value.
- Repository package/checklist/controller statuses are authoritative for this
  repository. A delivery skill's internal task states must be mapped to them
  and never replace or broaden them.
- Keep unrelated user changes intact. Parallel writes require explicit,
  disjoint file or domain ownership. Default to at most two active workers; a
  higher limit requires a recorded disjoint-work justification.

## Package-specific gates

For the active package, apply the selected delivery skill to a contract covering
its outcome, assumptions, scope and non-goals, acceptance criteria, verification,
entry points, review factors, and internal checkpoints.

- Obtain one independent plan review before implementation and one consolidated
  independent post-build review before package closure. A review required by a
  selected delivery skill satisfies the equivalent package gate when it covers
  the same unchanged contract or integrated diff, evidence, and risk class; do
  not duplicate a review solely because both layers name it.
- Money, privacy, security, native, and deployment checkpoints still require
  their named specialist reviews. These supplement rather than repeat the
  consolidated package review.
- Run deterministic tests and a live or end-to-end simulation proportional to
  risk. Contract changes update every baseline required by architecture §9;
  changes to those baselines rerun R14-B native contract fixtures.
- Amend architecture or decisions only for genuine design or product changes.
  In the same package change, update `docs/progress.md`, architecture tags and
  changelog, decision rows, and operational docs only where applicable, using
  concrete evidence rather than completion claims.
- Do not create iterative evidence-only commits. When committed evidence is
  required, write it once after implementation and verification stabilize; do
  not embed the containing commit's SHA in that same receipt.

Only when every owned checklist item is `DONE` may the controller close the
package, update both pointers, and promote the next dependency-safe package.
After PKG-09 closes, set the controller to `COMPLETE` and retain
PKG-09/W4-04B as the terminal evidence pointer.
