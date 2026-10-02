# Mobility repository delivery instructions

This file is the single active repository-wide instruction source. Global
`AGENTS.md` supplies universal coding policy; this file supplies only Mobility's
delivery authority, work tracking, and repository gates; the nearest nested
`AGENTS.md` may add stronger directory-specific rules. A selected delivery skill
owns the execution lifecycle and must apply all of those instructions without
restating or weakening them.

## Development stage and replacement policy

**Cardvert is still in development. There are no real users or live customer
data, and no production consumers depend on its existing interfaces.** Treat
current URLs, APIs, schemas, stored formats and behavior as development artifacts,
not compatibility commitments.

When the owner asks to change, replace or delete something, implement the new
design and remove the obsolete implementation within that scope. Do not retain
old URLs, redirects, aliases, API versions, compatibility shims, fallback paths,
dual formats or deprecated code solely to support hypothetical existing users.
Do not add migration, backfill, deprecation, backup or rollback work solely to
preserve obsolete development behavior or disposable demo/test data. Update
affected callers, links, tests, fixtures, seeds and documentation together so the
current design works end to end.

This owner direction supersedes earlier generic requirements to preserve old
URLs or backward compatibility for the requested replacement. Preserve a legacy
path only when the owner explicitly asks or a verified current external
integration requires it. Keep unrelated work, credentials and account-access
records intact; security, privacy, money correctness, delivery verification and
explicit approval for commits, external actions and deployment still apply.
Reassess these assumptions when the owner confirms real-user or production use.

## Required reading

Before planning or editing, read these sources in order:

1. `docs/client-decisions.md` — what the client wants now, by topic, with the
   history of every change and the D-row or Q-row that governs it.
2. `docs/requests.md` — every ask from the client, PM or owner and its status;
   the work register.
3. `docs/progress.md` — the build programme and launch gates: the package
   queue, external prerequisites and controller pointer.
4. `docs/architecture.md` §1, §30, §35, plus the sections the change touches —
   design, placement, remediation, and gates.
5. `docs/decisions-log.md` — the formal append-only decision record (Part 1)
   and questionnaire statuses (Part 2).
6. This root `AGENTS.md`.
7. The nearest nested `AGENTS.md` for the files being changed, such as
   `frontend/AGENTS.md`.

For launch-gate package work, also read the relevant package and checklist
criteria in `docs/delivery-contracts.md`. Its detail is binding; only
`docs/progress.md` controls that queue's order, statuses, dependencies and
external gates. `docs/archive/progress-history-2026-09.md` is historical
evidence.

A delegated worker reads only the exact excerpts, local rules, and source files
named in its bounded packet. The controller alone edits `docs/progress.md`.

## Account and access directory

Before work involving an external account, domain or deployment, read
`docs/account-access.md` for login links, access status, resource identifiers
and exact current credentials and CLI commands. This is a local document ignored
by Git. Update it when an account is onboarded or the owner supplies new access;
use the existing credentials without rotating them or reconnecting accounts
unless the owner asks. Keep the local document available to future agents.
Account access does not replace the delivery gates or owner authorization below.

## Owner and client work

All new work comes from the owner, relaying the client, the PM or their own
decisions. For each piece of work:

1. **Record it first.** Before any other edit, add a row to `docs/requests.md`
   following that file's rules (one row per ask, the next `REQ-NNN`).
2. **Record changed client rules.** When the ask changes what the client wants,
   update the topic in `docs/client-decisions.md` as that file describes: the
   old rule moves into dated history and the new rule cites its source. A change
   to product behaviour, money, privacy, eligibility or security also gets a
   new decisions-log D-row, the matching Part 2 Q-row update, and the
   architecture amendment, all in the same commit. Never invent a client value;
   an unanswered value stays unset and fails closed, and the question becomes a
   `NEEDS ANSWER` request.
3. Apply the delivery gates below. Locally, run only the
   test files the change touches.
4. **Merge only after full CI passes (D41).** With the owner's approval, push
   the branch and merge it into `master` only after the full GitHub CI run on
   that branch passes. Merge without squashing so the implementing commit keeps
   its SHA. Never leave several branches' full-suite evidence to one later run.
5. **Close it.** Mark the request `DONE` with the implementing commit, and add
   "Built in `<commit>`" to the topic history.

Commit, push, deployment, provider calls and any external-account action each
need the owner's explicit approval. Owner work does not move the launch-gate
package queue unless the owner explicitly reprioritises it. Keep unrelated user
changes intact. Parallel writes require explicit, disjoint file or domain
ownership. Default to at most two active workers; a higher limit requires a
recorded disjoint-work justification.

## Launch-gate programme

The original build programme is complete except for its launch gates:
`PKG-03 / W2-01C` (payment provider keys) and the external release, device,
pilot and handover evidence in PKG-08 and PKG-09. For work on those items:

- Implement only the package marked `NEXT`, `IN PROGRESS`, or `REVIEW` in the
  **Executable package queue**. There is exactly one active package. Inside it,
  implement only a runnable `TODO` selected by the package plan; the top
  `Current checkpoint` is a non-authorizing pointer.
- The 71 checklist items are acceptance obligations, not separate approvals or
  review cycles. The 22 `PARENT` rows are traceability only.
- `docs/next-steps.md`, architecture §31, old chats, TODOs, and
  `docs/build-loop/**` are context or historical evidence, not authority.
- Do not skip or reorder work silently. At promotion, use the dependency-safe
  scan and external-block rules defined in `docs/progress.md`; never invent an
  external value.
- Repository package/checklist/controller statuses are authoritative for this
  programme. A delivery skill's internal task states must be mapped to them
  and never replace or broaden them.

Only when every owned checklist item is `DONE` may the controller close the
package, update both pointers, and promote the next dependency-safe package.
After PKG-09 closes, set the controller to `COMPLETE` and retain
PKG-09/W4-04B as the terminal evidence pointer.

## Delivery gates

For every review-required change, apply the selected delivery skill to a
contract covering its outcome, assumptions, scope and non-goals, acceptance
criteria, verification, entry points, review factors, and internal checkpoints.

- Obtain one independent plan review before implementation and one consolidated
  independent post-build review before merging. A review required by a
  selected delivery skill satisfies the equivalent gate when it covers the same
  unchanged contract or integrated diff, evidence, and risk class; do not
  duplicate a review solely because both layers name it.
- Money, privacy, security, native, and deployment changes still require their
  named specialist reviews. These supplement rather than repeat the
  consolidated review.
- Run deterministic tests and a live or end-to-end simulation proportional to
  risk. Contract changes update every baseline required by architecture §9;
  changes to those baselines rerun R14-B native contract fixtures.
- Amend architecture or decisions only for genuine design or product changes.
  In the same change, update `docs/requests.md`, `docs/client-decisions.md`,
  architecture tags and changelog, decision rows, operational docs, and
  `docs/progress.md` (only when a launch gate or package status changes), where
  applicable, using concrete evidence rather than completion claims.
- Do not create iterative evidence-only commits. When committed evidence is
  required, write it once after implementation and verification stabilize; do
  not embed the containing commit's SHA in that same receipt.
