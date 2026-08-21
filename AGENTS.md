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
   money/privacy/security/native/deployment checkpoints.
3. Implement only that plan, using staged commits/checkpoints where useful.
   Amend architecture or decisions in the same
   change when implementation requires a genuine design or product decision.
4. Run deterministic tests plus a live/end-to-end simulation proportional to
   the risk. Contract changes move every baseline required by architecture §9,
   and any change to those baselines reruns R14-B's native contract fixtures.
5. Obtain one consolidated independent package post-build review. Specialist
   checkpoint reviews supplement it; they do not create owner-facing cycles.
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
