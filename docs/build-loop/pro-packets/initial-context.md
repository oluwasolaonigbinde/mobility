# Initial Pro Context Packet

## Request

You are Extended Pro reviewing the initial backend plan before implementation.

Decision to review:
Choose the backend stack and architecture for the Mobility AdTech & Audience Attribution Platform, produce the full backend slice roadmap, and provide the first approved Codex implementation prompt. No backend code has been scaffolded locally.

Please respond with:

- Verdict: SIGNED OFF or BLOCKED
- Backend stack decision
- Architecture summary
- Full backend slice roadmap
- First approved implementation prompt
- Required tests/checks for Slice 1
- Risks
- Reasoning notes

The first implementation prompt should be concrete enough for Codex to execute locally and should include allowed scope, explicit non-goals, expected files or modules, tests/checks, acceptance criteria, and the stop condition.

## Project

Mobility AdTech & Audience Attribution Platform

## Product Goal

Build the backend for a mobility advertising platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, the system ingests GPS movement data, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

## Product Brief Summary

The product transforms shared ride vehicles into measurable advertising and audience-generation assets using GPS analytics, impression estimation, dynamic driver incentives, geospatial targeting, and future audience retargeting.

Core MVP areas:

- Advertisers create and manage campaigns.
- Campaign creatives and target zones/geofences are tracked.
- Drivers and vehicles activate assigned campaigns.
- Driver GPS movement is ingested as pings and organized into trips, sessions, or routes.
- Route analytics estimate campaign exposure and impressions using traffic density, route, road category, time of day, dwell time, and exposure scoring.
- Driver payouts are calculated from mileage, target zone presence, traffic density, and exposure quality.
- Advertisers receive dashboard summaries, campaign reporting, and heatmap-ready geospatial data.
- Basic fraud/anomaly flags detect GPS spoofing, repetitive route loops, and fake movement.

Deferred/future scope unless explicitly approved for a later slice:

- Offline-to-online retargeting
- Anonymous audience pooling
- AI/computer vision counting
- Advanced ML fraud detection
- Real automated driver payout settlement
- Frontend implementation
- Mobile app implementation
- Production cloud deployment

## Confirmed Starting Repo State

Local path: `C:\Sola Files\Sola Old\mobility`

Local git branch after initialization: `master`

Starting files before ledger setup:

- `agent.md`
- `Developer_Product_Brief_Mobility_AdTech(1).docx`

Important repo note:

- The orchestration brief refers to `AGENTS.md`.
- The actual local file is named `agent.md`.
- Its document title is `AGENTS.md - Core Coding Guidelines`.
- Treat `agent.md` as the local constraints source unless the roadmap explicitly instructs a safe normalization.

Current ledger files created:

- `docs/build-loop/README.md`
- `docs/build-loop/product-brief.md`
- `docs/build-loop/slice-log.md`
- `docs/build-loop/pro-packets/initial-context.md`
- Empty ledger directories for prompts, reports, and Pro responses

No backend stack, architecture, package manager, database schema, API framework, source tree, or tests have been implemented.

## Local Constraints From `agent.md`

- Do not assume vague context; surface tradeoffs and state assumptions.
- Prefer simplicity and minimal code.
- Avoid speculative features and single-use abstractions.
- Keep diffs small and focused.
- Match local style once code exists.
- Define success criteria and make tasks testable.
- For implementation tasks, use a checklist and update it progressively.
- Use subagents only when parallel read-only investigation or review materially speeds up the task.
- Keep edits single-owner unless write scopes are explicitly disjoint.

## Orchestrator Constraints

- Use local git.
- Do not require GitHub.
- Do not create a GitHub repo, push, or add remotes unless explicitly requested.
- Do not scaffold backend code until Pro provides the stack decision, full backend roadmap, and first approved implementation prompt.
- Every future slice prompt must be reconciled against the product brief summary, saved Pro roadmap, local constraints, current repo state, and previous slice-log entries.
- If any Pro instruction conflicts with local evidence, stop and create a reconciliation report instead of implementing blindly.

## Requested Output

Please produce:

1. Backend stack decision with rationale.
2. Backend architecture summary.
3. Full backend slice roadmap covering the build-now target areas.
4. First approved Codex implementation prompt.
5. Required tests/checks for Slice 1.
6. Explicit non-goals for Slice 1.
7. Acceptance criteria for Slice 1.

Focus on MVP backend execution and reviewable slice order. Do not expand into deferred/future scope unless you explicitly identify it as out of scope for this build loop.
