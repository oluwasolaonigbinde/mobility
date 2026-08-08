# Progress — Delivered Work vs. the MVP Promise

**The evolving "what exists so far" doc.** Agents update this file in the same
commit as any landed slice: move items between the sections below, date them,
and keep the wave position current. Detail lives elsewhere — this file is the
summary layer (replaces `project-reconciliation.md`, 4 Aug 2026).

The endpoint we are building toward is fixed by
`docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx` (scope, D11) as
designed in `docs/architecture.md` (target state + §31 wave sequencing).

## Canonical repository

`/Users/oluwasolaonigbinde/Projects/mobility` on `master`. The former
`mobility-master` directory was an obsolete Slice-0-only copy — never use it
to determine delivery status. When documentation conflicts, committed source
and Git history win.

## Delivered so far

| Stream | Status | Evidence |
| --- | --- | --- |
| Backend slices 0–13 (closed loop) | Complete | `docs/build-loop/slice-log.md`; closure commit `0dfb284` |
| Frontend F0–F6 (advertiser/driver/admin surfaces) | Complete — **driver PWA tracking has 2 verified defects** (§35 RM4/RM5) | Git `9189fe4`…`a5bcbb6`; `docs/archive/fablev1-work.md` journal |
| F7 auth/session hardening + audit + CI + backups | Complete, merged | Git `f40e0c4`…`236c2e4` (PR #1); architecture changelog v1.4 |
| Automated post-trip pipeline (arq worker) | Complete, merged | Git `159b0b1`, `4f69ef6`; architecture v1.5–v1.6 |
| S1 — payout engine v2 (hourly pay + daily caps, D2/D4/D9) | Complete, merged — RM1 fixed + RM2 half fixed (6 Aug, migration `0015`); **RM6 and RM2's sub-window half still open** | Git `f9cd8ca`; architecture v1.8/v1.15, §16.1 [BUILT] |
| S4 — data lifecycle (ping partitions, retention purge, audit backfill, D10) | Complete, merged | Git `a879a3d`…`4f487e7`; architecture v1.9, §24.2 [BUILT] |
| Pre-production ops (production Compose overlay, release smoke, backup/restore rehearsal) | Complete locally, **not deployed** | Git from `006d94e`; `docker-compose.production.yml`, `docs/runbook.md` |
| Current API contract | 15 migrations, contract baselines current | `docs/api/openapi.snapshot.json` + `openapi.json` + `schema.d.ts` drift checks |

**Nothing is deployed.** Staging/production remain research-only
(`docs/staging-options.md`) pending provider, budget, and operator approval
(Q32).

## Where we are in the roadmap (architecture §31)

- **W0 — review remediation (new, 6 Aug 2026, D13):** **in progress** — RM1
  (cross-midnight cap allocation) fixed and RM2's renewable-grace half fixed,
  6 Aug 2026 (migration `0015`, 455 tests green on PostGIS). It leads the
  remaining work. An independent code-verified review found **seven live defects in
  already-built code** (architecture §35.1) plus eleven specification rows for
  unbuilt domains. The live ones — cross-midnight cap allocation, stationary
  time farming, no trip-seal protocol, ping double-insert on retry, in-memory
  ping buffer, single-admin retroactive repricing, integrity error mapping —
  gate real-driver GPS and any earnings release (§35.3). Still open: RM2's
  sub-window stationary aggregation (needs a money-policy decision), RM3–RM7.
- **W1 — money correctness:** worker ✅, payout v2 ✅ (S1), data lifecycle ✅
  (S4). **Remaining: S2 fraud review + holds (§17, Q21 — must implement RM8),
  S3 release scheduling + payout runs UI (§16.2/§16.3, Q22, Q27 — must
  implement RM10/RM11).** Slice direction: `docs/next-steps.md`.
- **W2 — commercial layer:** not started. Billing/invoices (§15, S5 opener),
  file storage (§19), campaign/creative approval + installation evidence
  (§18), notification channels (§20).
- **W3 — reach:** not started. Retargeting at full Module G scope (§22),
  matching recommender + activity sweeps (§21), driver self-registration
  (§23).
- **W4 — mobile app + pilot readiness (D11):** not started. Driver mobile app
  (React Native/Flutter, background GPS, push), remaining CSV/PDF exports,
  pilot deployment, onboarding/training materials.

## Promise vs. delivery, by proposal module

| Proposal module | Delivered | Outstanding (wave) |
| --- | --- | --- |
| A. Admin platform | Login/RBAC, user+org onboarding, drivers/vehicles, assignments, fraud-flag console, payout rules UI, traffic profiles, audit UI | Campaign/creative approval queues (W2), installation evidence (W2), payout release ops (W1-S3), retargeting monitoring (W3), exports (W4) |
| B. Advertiser dashboard | Campaigns CRUD, zones editor, analytics, heatmaps, reports + charts, cost summaries | Creative *upload* (W2 — metadata-only today), billing/invoices (W2), retargeting setup + insights, exposure score + high-exposure zone views (W3), CSV/PDF export (W4) |
| C. Driver app | Installable PWA: jobs, live trip tracking (idempotent ping batches), earnings + S1 trip breakdown, profile | Offer accept/decline (W3 §21), self-registration (W3), notifications (W1-S2 minimal → W2 channels), **mobile app** (W4) |
| D. Analytics & impression engine | Route analytics, fraud flags, impression estimates, exposure/heatmap aggregation, payout eligibility classifier | Exposure score metric (`exposure_v1`) + high-exposure zone identification + retargeting insight capture (W3) |
| E. Dynamic driver payouts | Payout v2 hourly engine, caps, write-once calcs, recompute-day, ledger | Fraud hold/review (S2), release scheduling + weekly batch + payout report (S3, Q27) |
| F. Heatmaps & reporting | Campaign heatmaps, route visualization, report screens, daily metrics | High-exposure zone + follow-up-targeting report sections (W3), CSV/PDF export (W4) |
| G. Online-to-offline retargeting | — (privacy boundary designed, §22) | Entire module (W3): sources, segments, linkage, insights; export gated on Q31 |

## Documentation authority

| Question | Source of truth |
| --- | --- |
| What the MVP must deliver | `docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx` (D11) |
| How it is designed (current + target) | `docs/architecture.md` |
| Product decisions + Q1–Q34 statuses | `docs/decisions-log.md` (Part 1 history, Part 2 statuses) |
| What has been delivered so far | this file (summary) → architecture changelog + Git for detail |
| How to operate it | `docs/runbook.md` |
| Historical evidence | `docs/build-loop/` (closed backend ledger), `docs/archive/` |

## Update rules

1. A landed slice updates this file in the same commit: delivered-so-far row,
   wave position, and the module table.
2. Client answers land in `decisions-log.md` first; if they change scope or
   design, `architecture.md` amends in the same commit — this file only
   records resulting *delivered* changes.
3. The next expected status changes: S2 (fraud review), then S3 (release
   scheduling); or an approved staging deployment (records provider, budget,
   operator per `docs/staging-options.md`).
