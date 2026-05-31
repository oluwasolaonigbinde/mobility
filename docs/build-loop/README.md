# Build Loop Ledger

This directory is the local build-loop ledger for the Mobility AdTech & Audience Attribution Platform backend.

## Purpose

The project is starting from a greenfield repo with only a local agent constraints document and the client product brief. This ledger keeps product context, Pro review packets, Pro responses, implementation prompts, slice reports, and slice status in one reviewable place.

## Authority Model

- Pro is the external decision-making reviewer for stack choice, architecture, MVP boundaries, slice order, and acceptance decisions.
- The local orchestrator owns repo truth, git workflow, implementation coordination, evidence gathering, and reconciliation.
- Implementation workers may implement only approved slices. They must not choose the stack, expand scope, or implement future features.
- Local repo evidence wins over blind obedience. If a Pro instruction conflicts with current files, product scope, or constraints, stop and write a reconciliation report.

## Local Evidence Sources

- Product brief summary: `docs/build-loop/product-brief.md`
- Local constraints: `agent.md`
- Pro roadmap source of truth, once received: `docs/build-loop/pro-responses/initial-roadmap.md`
- Slice tracking: `docs/build-loop/slice-log.md`
- Approved slice prompts: `docs/build-loop/prompts/`
- Implementation reports: `docs/build-loop/reports/`
- Pro packets: `docs/build-loop/pro-packets/`
- Pro responses: `docs/build-loop/pro-responses/`

Note: the local constraints file currently exists as `agent.md`, although its document title is `AGENTS.md`. Pro packets should report this exact repo state.

## Build Rules

- Do not scaffold backend code until Pro provides a backend stack decision, a full backend slice roadmap, and a first approved Codex implementation prompt.
- Build only the currently approved slice.
- Keep slices small enough to review.
- Reconcile every Pro prompt against the product brief, saved Pro roadmap, local constraints, current repo state, and prior slice-log entries.
- If a prompt is unsafe, ambiguous, or inconsistent with local evidence, stop and write a reconciliation report.
- Use local git only. Do not create a GitHub repo, add remotes, push, or require GitHub unless explicitly requested.

## Deferred Scope

Do not implement these unless Pro explicitly approves them for a current slice:

- Offline-to-online retargeting
- Anonymous audience pooling
- AI or computer vision counting
- Advanced ML fraud detection
- Real automated payout settlement
- Frontend implementation
- Mobile app implementation
- Production cloud deployment

## Per-Slice Gate

Each slice should finish with:

- An implementation report under `docs/build-loop/reports/`
- Required tests or checks run, with results recorded
- A self-contained Pro review packet under `docs/build-loop/pro-packets/`
- Pro response saved under `docs/build-loop/pro-responses/`
- A local commit only after Pro returns PASS and local reconciliation agrees
