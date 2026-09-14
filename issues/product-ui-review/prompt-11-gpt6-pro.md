# Prompt 11 — GPT-6 Pro consolidated implementation backlog

MODEL GATE: GPT-6 Pro, maximum/deepest available reasoning.

You are the final independent synthesis reviewer for the Cardvert UI/product
programme. Produce a bounded, de-duplicated implementation programme from ten
completed audits and their adversarial PRD review. This is a read-only planning
task, not an implementation task.

## Repository and immutable code authority

- GitHub repository: https://github.com/oluwasolaonigbinde/mobility
- Branch: `master`
- Exact commit: `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`

Use the connected GitHub repository to confirm and inspect that exact commit.
State the complete SHA actually inspected. If the connector cannot access that
commit, stop and report the access problem. Do not substitute current `master`,
another branch, an older cached revision, or a locally inferred snapshot.

## Attached programme evidence

I have attached `cardvert-ui-product-review-evidence-5f84194.zip`. Read every
file in it. It contains the controller's local programme state that is not part
of the immutable GitHub commit:

- the programme README and status;
- canonical prompts;
- Prompt 1–10 answers/controller captures;
- normalized outcomes;
- reconciliation rules; and
- proposed packets.

The archive supplies review provenance; GitHub supplies code truth. Treat audit
claims as leads rather than proof. Where a claim matters to priority, scope, or
acceptance, verify it against the exact GitHub commit. If the archive is missing
or unreadable, stop rather than synthesize from this prompt alone.

## Objective

Convert the completed system-flow, UI, copy, operations, advertiser, driver,
state/error, external-boundary, PRD, and adversarial-review work into the
smallest coherent implementation backlog that improves the real product without
redesigning it unnecessarily.

Reconcile duplicate, conflicting, speculative, stale, unsupported, already
delivered, externally gated, and owner-dependent claims. Preserve existing
security, privacy, money, evidence, concurrency, audit, and fail-closed
boundaries. Do not weaken a legitimate gate merely to make the interface feel
smoother.

## Sealed Prompt 10 authority

Use `answers/prompt-10-adversarial-prd-review.md` as the sealed handoff. In
particular:

- consume accepted corrections RC-01–RC-15;
- preserve the unresolved `VERIFY` list as verification work rather than fact;
- preserve all named owner/external gates;
- obey the explicit duplicate/dismissed list;
- retire `FUX-007`: mobile account controls were delivered at `a73556c` and
  remain present at the audited baseline;
- treat `ADV-006` as a confirmed P1 commercial-consent gap: material quotation
  fields are returned but not displayed before immutable acceptance;
- treat `CPY-001` as an observed naming contradiction whose resolution is an
  owner decision;
- do not claim zone-tiered base/premium pay is unbuilt: `payout_v3` is present;
- do not convert Prompt 10's client-document P0 labels into software P0s; and
- do not create implementation slices for diagram/editorial corrections unless
  an actual shipped-product defect independently requires one.

## Required analysis

Trace each admitted item across the relevant user journey, frontend route or
component, API contract, backend service/database authority, existing tests and
external dependencies. Search for newer or contradictory source evidence at the
exact commit. Cross-reference an existing outcome ID whenever possible instead
of inventing another identifier.

Organize the admitted work under these lenses:

1. critical broken flows;
2. expected gates rendered incorrectly as failures;
3. misleading, internal, or AI-facing copy;
4. information architecture and navigation;
5. advertiser workflow;
6. driver workflow;
7. operations workflow;
8. cross-module state consistency;
9. accessibility, offline behavior and recovery; and
10. client-document corrections.

These lenses may cross-reference the same slice. They must not duplicate it.

## Classification rules

Classify every source finding exactly once as:

- `FIX` — source-supported, user-visible or operational defect with a bounded
  correction;
- `VERIFY` — plausible but requiring deterministic reproduction, manual/device
  evidence, or additional source proof before implementation;
- `DEFER` — useful but dependent on real user/operator research or lower-value
  optional design work;
- `DISMISS` — false, stale, cosmetic-only, duplicate without independent scope,
  or already delivered;
- `OWNER DECISION` — Terrax Media must choose the product/operating policy; or
- `EXTERNAL INPUT` — legal, provider, permit, commercial, support, logistics,
  device, staging or real-world evidence must be supplied.

Do not use `FIX` as a catch-all. An owner/external dependency may be a gate on a
future fix, but the missing value itself is not software work.

## Backlog requirements

Create the smallest set of cohesive vertical slices. For every proposed `FIX`
slice provide:

- stable slice ID and concise title;
- source outcome IDs and duplicate aliases absorbed;
- user-visible outcome;
- evidence at the exact commit, including paths and precise symbols or lines;
- affected roles and complete journey/state transition;
- frontend routes/components, API contracts, backend services and data
  authorities likely involved;
- exact wording change where wording is sufficiently authorized;
- behavior and safety boundaries that must remain unchanged;
- important break cases;
- acceptance criteria;
- deterministic automated regression coverage, including required red/green or
  mutation evidence;
- manual, browser, accessibility, responsive, offline or physical-device
  verification as applicable;
- dependencies and dependency-safe execution order;
- collision/overlap risk with other slices;
- owner/external gate;
- specialist review required for money, privacy, security, device or legal
  boundaries; and
- risk classification P0–P3, with P0 reserved for demonstrated immediate
  security, privacy, safety or irreversible-money harm.

For every `VERIFY`, state the exact evidence needed and the disposition if the
claim fails reproduction. For every `OWNER DECISION` or `EXTERNAL INPUT`, give
the precise question/input, the party that supplies it, the work it blocks, and
the safe current behavior. For every `DISMISS`, give the reason and the existing
ID or delivery evidence that prevents re-entry.

## Scope boundaries

- Read-only: do not modify code, files, issues, branches, commits or pull
  requests.
- Do not claim to run tests, databases, browsers, devices, providers, CI or
  deployments. GitHub inspection is static.
- Do not reopen the R01–R60 engineering programme unless a current source-backed
  regression directly overlaps a proposed slice.
- Do not invent legal copy, bank/payment details, rates, support contacts,
  provider identities, permit status, retention periods or real-world logistics.
- Do not propose new RBAC roles merely because the audits list many operational
  responsibilities.
- Do not turn broad visual taste, emoji, typography preference, dashboard
  composition, payout subnavigation or driver earnings hierarchy into defects
  without user evidence.
- Do not treat every backend/API capability without a browser screen as a defect;
  confirm that browser operation is part of the accepted pilot operating model.
- Do not duplicate `CPY-002`, `FUX-005`, `FUX-006`, `NX-16`, `NX-17` or another
  cross-cutting family for each surface symptom.

## Output

Return one self-contained report with:

1. Exact baseline and evidence-pack confirmation.
2. Coverage matrix mapping all Prompts 1–10 and every normalized outcome family
   to a disposition.
3. Contradictions or stale claims corrected before backlog creation.
4. Final de-duplicated slice backlog, ordered by dependency and risk.
5. Separate `VERIFY` queue with exact reproduction plans.
6. Separate owner-decision and external-input register.
7. Explicit dismissed/already-delivered/duplicate register.
8. Top ten highest-value changes.
9. Quick wins versus structural work, without reordering required dependencies.
10. Recommended execution model: which slices may run in parallel and which
    must remain sequential, with exact collision domains.
11. Specialist-review map.
12. Client-PRD correction register derived from RC-01–RC-15; do not rewrite the
    whole PRD unless necessary to remove a contradiction.
13. Definition of done for the complete UI/product cleanup programme.
14. Final verdict: `READY TO PACKAGE`, `NEEDS MORE VERIFICATION`, or
    `BLOCKED ON OWNER/EXTERNAL INPUT`, distinguishing executable software work
    from launch/deployment readiness.

Finish with a sealed handoff for the local repository controller containing only
the admitted slices, dependency order, verification gates, owner/external
blocks, dismissals and explicit no-duplication rules. Do not implement anything.
