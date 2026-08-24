# Repository delivery instructions

This repository is delivered as one reviewed package at a time. Before planning
or editing anything, read these sources in order:

1. `docs/progress.md` — the operational delivery control and sole work queue.
2. `docs/architecture.md` §1, §30, §35, and the active package/checkpoint's referenced
   sections — design, placement, remediation requirements, and gates.
3. `docs/decisions-log.md` — adopted product decisions and divergence guards.
4. `agent.md` — repository-wide coding guidelines.
5. The nearest nested `AGENTS.md`, when editing inside a directory that has
   one (for example `frontend/AGENTS.md`).

After those authorities, consult only the active-package and inherited-seam
sections of `docs/pro-review-register.md`. It is advisory revalidation context,
never a second queue, architecture source, decision log, or implementation
authorization.

The full reading order above applies to the active controller. A delegated
worker receives a bounded task packet and reads only the exact global sections,
local rules, and source files named in that packet. Workers must not reread the
entire global control documents unless the controller records why that is
necessary for their specific task.

## Delegation context and usage budget

These rules are mandatory for every controller and survive chat/session
handoffs:

- Spawn every subagent with **no inherited conversation history** by default.
  In Codex, explicitly set `fork_turns: "none"`; never rely on the tool's
  full-history default. A bounded positive turn count is allowed only when the
  controller records why a self-contained packet cannot carry the required
  facts. Full-history delegation requires explicit project-owner authorization
  for that exact delegation.
- Give each worker one compact, self-contained task packet. It contains only:
  task/outcome, exact base/ref, relevant decision IDs or short excerpts, allowed
  reads, allowed writes, acceptance criteria, focused verification, stop
  conditions, and the required result format. Link to commits and files instead
  of pasting chats, ledgers, test logs, or prior agent reports.
- A worker may not reconstruct, request, or receive the controller's full chat
  or full plan-ledger. If a missing fact materially blocks the task, it returns
  one focused question; the controller answers with only that fact.
- The controller is the only agent that reads and maintains the complete
  programme ledger and global delivery state. Read-only scouts get one bounded
  question. Reviewers get the approved contract, the exact diff/commit range,
  and the relevant evidence only.
- Do not delegate duplicate discovery or duplicate review. Parallel agents must
  have genuinely disjoint questions or write ownership. Parallelism is for
  throughput, not for having several agents ingest the same repository context.
- Default to at most two active workers: one implementation worker and one
  disjoint scout or required reviewer. More concurrent workers require an
  explicit, recorded justification based on disjoint work; available capacity
  alone is not justification.
- Use the smallest capable model: Luna for bounded searches, inventories and
  focused checks; Terra for ordinary implementation and review; Sol/high
  reasoning only for demonstrably difficult money, security, migration,
  concurrency or package-boundary decisions. Pro use must be explicitly
  justified by marginal risk/quality value.
- Run focused tests inside slices. Run the full relevant suite once at the
  integration/package gate unless a failure or shared-boundary change requires
  another run. Do not have multiple agents repeat the same full suite or ingest
  repeated CI-watch output.
- Keep worker responses bounded: verdict, changed paths/commit, acceptance
  evidence, concise test results, and real blockers. Store verbose evidence in
  files and return pointers. The controller reports only material events to the
  user.
- Before expensive delegation, check remaining usage when the surface exposes
  it. When capacity is low or unknown, serialize work and prefer Luna/local
  tooling. Never trade the user's weekly allowance for speculative reviews,
  reviewer-of-reviewer loops, or governance ceremony.

Every controller handoff must restate the no-history spawning rule and the
current worker/model/concurrency budget. A successor must apply these rules
from repository state, not rely on remembering a previous conversation.

## The execution lock

- Implement only the package marked `NEXT`, `IN PROGRESS`, or `REVIEW` in the
  **Executable package queue**. There is exactly one active package. Inside it,
  implement only a runnable `TODO` checklist item selected by the package plan;
  the top `Current checkpoint` is the controller's non-authorizing pointer.
- The 71 checklist items are mandatory acceptance obligations, not 71 separate
  owner approvals or review cycles. The 22 `PARENT` rows are traceability only.
- Do not select work from `docs/next-steps.md`, §31's broad waves, an old chat,
  a TODO, or personal judgement. They are context, not authorization.
- Do not skip or reorder the queue silently. A direct project-owner request
  may reprioritize it, but update `docs/progress.md` first and record why.
- At promotion, scan packages in order. A blocked earlier package may be bypassed
  only for a later package with a runnable checklist checkpoint whose transitive
  checklist dependencies are `DONE`. Record every missing external input as
  `BLOCKED — EXT-ID`; never invent a value.
- A package is `BLOCKED` only when every unfinished item is blocked or depends
  on blocked work. If no package has runnable work, set `PAUSED — EXT-ID`.
- Keep unrelated user changes intact. One package owns one controlled program;
  internal parallel work must have explicit disjoint file/domain ownership and
  only the controller edits `docs/progress.md`.

## Package loop

1. Restate the active package as a delivery contract: outcome, assumptions,
   scope/non-goals, acceptance criteria, verification, entry points, and
   relevant review factors. Expand its checklist into internal checkpoints.
2. Inspect the current implementation and write a bounded package plan. Obtain
   one independent plan review before implementation, plus specialist review at
   money/privacy/security/native/deployment checkpoints. From PKG-04 onward, as
   part of that one plan review, build and challenge the applicable
   adversarial-boundary matrix described in `docs/pro-review-register.md`.
   Select only boundaries touched by the planned change; cite the controlling
   architecture/decision/package
   contract for every invariant, and record concrete ordering, retry,
   conservation, identity, migration or producer/consumer failure cases plus
   their focused regression evidence. A considered category may be marked
   `not applicable` with a short reason. The matrix lives in the bounded
   package plan or its review record; it is not another queue, checklist status,
   approval cycle or source of product decisions. Resolve material gaps before
   coding, or record the authoritative blocker/deferral without expanding the
   active package.
3. Implement only that plan, using staged commits/checkpoints where useful.
   Amend architecture or decisions in the same
   change when implementation requires a genuine design or product decision.
4. Run deterministic tests plus a live/end-to-end simulation proportional to
   the risk. Contract changes move every baseline required by architecture §9,
   and any change to those baselines reruns R14-B's native contract fixtures.
5. Obtain one consolidated independent package post-build review. Specialist
   checkpoint reviews supplement it; they do not create owner-facing cycles.
   Treat this review as confirmation of the pre-implementation boundary work.
   If it discovers a genuinely new high-confidence composition pattern, the
   controller must first reproduce and reconcile it against the active base and
   authoritative contract, then add only the reusable pattern to
   `docs/pro-review-register.md` for later packages. Do not reopen unrelated
   completed packages merely to apply a newly recorded pattern.
6. In the same change set, update `docs/progress.md`, architecture tags and
   changelog where applicable, decision rows where applicable, and operational
   docs. Record concrete evidence, not a completion claim.
7. Only when every owned checklist item is `DONE`, mark the package `DONE`,
   update both pointers, and promote the next dependency-safe package. Never
   promote a checklist item or parent row. A package closure commit is the
   boundary when the task authorizes commits. After PKG-09 closes, set the
   controller to `COMPLETE` and retain PKG-09/W4-04B as the terminal evidence
   pointer; do not invent another package.

No package or checklist item is `DONE` merely because code was written. It is
done when behaviour, verification, review, evidence, and documentation agree.
