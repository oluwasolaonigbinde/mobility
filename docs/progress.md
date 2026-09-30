# Build Programme and Launch Gates

**For current work, start with [client-decisions.md](client-decisions.md)
(what the client wants now) and [requests.md](requests.md) (every ask and its
status).** This file is the ledger of the original build programme. That
programme is complete except for its launch gates: public/production
payment-provider evidence (`PKG-03 / W2-01C`) and the external release, device,
pilot and handover
evidence in PKG-08 and PKG-09. For that programme, **this file alone controls
which package may be executed next**, and its registers below are what the
pilot-gate and handover tooling checks. The proposal owns scope, architecture
owns design, decisions-log owns the formal decision record, and Git/test
evidence proves delivery.

The endpoint is the D11 proposal scope as superseded by direct client answers
and later approved decisions in `docs/decisions-log.md`, designed in
`docs/architecture.md`. D18–D20 resolved Q1–Q34; subsequent D-rows govern
their own changes. Architecture §31 is roadmap context; execution order and
authorization live exclusively in this document.

**Package:** one owner-facing delivery/review cycle. **Checklist item:** one of
the 71 original mandatory implementation obligations inside a package; it is
never an authorization unit. **Remediation slice:** one of the 60 owner-admitted
fix units in PKG-10; its immutable candidate and dependency mapping is the
authorization boundary. **Parent:** one of the 22 architecture traceability
groups; it is never executable. **Active slot:** the single package marked
`NEXT`, `IN PROGRESS`, or `REVIEW`.

## Execution lock

Package status is `QUEUED | NEXT | IN PROGRESS | REVIEW | DONE | BLOCKED`.
Checklist status is `TODO | DONE | BLOCKED — EXT-ID`; checklist items never use
package-active vocabulary. A package is `DONE` only when all its checklist items
are `DONE`. It is `BLOCKED` only when every non-DONE item is externally blocked
or transitively depends on blocked work and no runnable `TODO` remains.

The active package moves through `NEXT → IN PROGRESS → REVIEW → DONE`. Its
controller selects the current runnable checklist checkpoint, honors the
applicable dependency graph, and may use staged commits and parallel agents with
explicit disjoint ownership. PKG-10 slice state is `QUEUED | ACTIVE | COMPLETE`;
two dependency-ready, write-disjoint slices are the baseline; a larger current
capacity is valid only when the exact active slice set and disjoint-work
justification below are recorded before dispatch. Its displayed current
checkpoint is a controller pointer, not a claim that only one slice is ready.
A slice becomes `COMPLETE` only after its own plan review, diff review,
and named domain checkpoint have accepted evidence. Money, privacy, security,
client-device, deployment and other high-risk checkpoints receive specialist
review before integration; one consolidated independent package review closes
the owner-facing cycle.

**Current justified remediation writer capacity:** `2`
**Current capacity assignment:** ``
**Current capacity justification:** All 60 remediation slices are accepted and
the 86 FIX / 29 non-executable disposition reconciliation is closed. No further
remediation writer is authorized; the repository returns to its first unresolved
external checkpoint.

`Controller state` is `COMPLETE` only after all ten packages are `DONE`, all 71
original checklist items are `DONE`, and all 60 remediation slices are
`COMPLETE`. Retain `PKG-09` as the final control package and `PKG-09 / W4-04B`
as the terminal evidence pointer, as required by the repository execution
authority; PKG-10/R60 remains the remediation closure receipt. This is the only
valid zero-active state other than an explicit external pause.

At promotion, scan packages in order. A blocked earlier package does not freeze
the program: promote the first later package containing a runnable checklist
item whose transitive checklist dependencies are `DONE`. Never use invented or
placeholder external values. Only an owner-recorded decision clears a checklist
external block. If the active package has no runnable item, mark it `BLOCKED`,
report every blocking `EXT-ID`, and either promote a dependency-safe later
package or set the controller `PAUSED — EXT-ID` only when no runnable `TODO`
exists anywhere. A pause ID must be registered `MISSING` and must directly or
transitively block the pointed package/checkpoint.

External prerequisites distinguish build-entry inputs from live-use gates in
their “exact effect” text. Only an external ID named in a checklist item's
prerequisite cell blocks building that item; launch facts and legal approvals
that gate live use do not prevent provider-neutral or synthetic implementation.

### Current control pointer

**Controller state:** `PAUSED — EXT-PAYMENT-PROVIDER`
**Control package:** `PKG-03` — local sandbox checkout and provider wiring are implemented; the remaining gateway checkpoint requires public-edge webhook/recovery evidence and production provider authority.
**Current checkpoint:** `PKG-03 / W2-01C` — blocked by the remaining parts of `EXT-PAYMENT-PROVIDER`.

PKG-08 and PKG-09 await the external release, provider, physical-device and pilot evidence named in their checklist rows. PKG-10 remediation is complete. The queue and registers below hold the exact current state.

## Direct owner requests outside the package queue

**Progress-document reorganization (29 Sep 2026):** The owner approved this shorter present-day control page. Dated receipts are in [the September delivery history](archive/progress-history-2026-09.md); detailed package and checklist criteria remain live in [delivery-contracts.md](delivery-contracts.md). The package queue, checklist statuses, dependencies, external gates and controller pointer retain their authority and values.

**Owner and client work (from 29 Sep 2026):** Every ask from the client, PM or
owner is recorded and tracked in [requests.md](requests.md), and client rules
by topic in [client-decisions.md](client-decisions.md); root `AGENTS.md` sets
the flow. Batches A–E of the Cardvert next build pass (D38–D41) are merged and
recorded there as REQ-001 to REQ-006; Batch F is REQ-009 to REQ-012. Their
contracts and evidence are in [the delivery history](archive/progress-history-2026-09.md).
This work does not promote or reorder the paused package queue. Open client
parameters stay fail-closed; `payout_v1`–`v3` history is never repriced.
Commit, push, deployment, provider calls and external-account action require
separate owner approval.

**Branch acceptance (D41, 29 Sep 2026):** Each future batch or feature branch must pass its full GitHub CI run before merging into `master`; local runs cover touched test files. The adopted coverage floors and D32 thresholds remain unchanged. See [D41](decisions-log.md) for the exact tolerance policy.

## Executable package queue

| # | Package | Status | Outcome | Package prerequisites |
| ---: | --- | --- | --- | --- |
| 1 | **PKG-01 — foundations and empirical risk proof** | DONE | Resolve remaining foundations, production-PWA/staging risk and correction authority. | none |
| 2 | **PKG-02 — money integrity and payout operations** | DONE | Corrected release, pre-existing-reversal backfill and debt-aware economic/settlement authority agree. | none — checklist DAG gates entry |
| 3 | **PKG-03 — commercial contracts and billing** | **BLOCKED** | Synthetic/provider-neutral commercial flow and configurable budget enforcement are verified; only `W2-01C BLOCKED — EXT-PAYMENT-PROVIDER` remains unfinished. | none — checklist DAG gates entry |
| 4 | **PKG-04 — secure evidence, activation and communications** | **DONE** | Provider-neutral storage/KYC/activation, shared notifications, business triggers, audited driver contact and account recovery are verified; live providers remain gated. | none — checklist DAG gates entry |
| 5 | **PKG-05 — privacy, measurement and retargeting** | **DONE** | Privacy controls and reproducible measurement govern aggregate retargeting, exposure scores and advertiser insights; live privacy/methodology/platform inputs remain gated. | none — checklist DAG gates entry |
| 6 | **PKG-06 — matching and driver onboarding** | **DONE** | Recommendations, offers, activity, public application, person/payee onboarding and governed vehicle approval form one verified work-eligibility journey. | none — checklist DAG gates entry |
| 7 | **PKG-07 — production driver PWA** | **DONE** | The installable pilot PWA safely tracks, syncs and completes the governed onboarding, campaign, earnings and dispute journey; physical-device/live release evidence remains explicitly deferred. | none — checklist DAG gates entry |
| 8 | **PKG-08 — governed reporting and pilot readiness** | **BLOCKED** | Provider-neutral reporting, release preparation and synthetic pilot acceptance are reviewed and complete; only registered external deployment, provider, approval, device and pilot evidence remains. | none — checklist DAG gates entry |
| 9 | **PKG-09 — controlled pilot, training and handover** | **BLOCKED** | Provider-neutral training, pilot-operations and handover preparation is integrated and reviewed; only rehearsed training, controlled-pilot evidence, named-owner acceptance and protected handover remain. | none — checklist DAG gates entry |
| 10 | **PKG-10 — admitted Cardvert audit remediation** | **DONE** | All 86 admitted FIX candidates are delivered and verified once through the exact R01–R60 dependency graph; all 29 non-executable dispositions remain preserved. | none — remediation DAG gates entry |


## Executable package contracts

The detailed criteria in [delivery-contracts.md](delivery-contracts.md#package-contracts) remain live. Status and authorization are controlled by the queue above.

### PKG-01 — foundations and empirical risk proof

- **Owns:** checklist 1–9.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-02 — money integrity and payout operations

- **Owns:** checklist 10–18.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-03 — commercial contracts and billing

- **Owns:** checklist 19–27.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-04 — secure evidence, activation and communications

- **Owns:** checklist 28–43.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-05 — privacy, measurement and retargeting

- **Owns:** checklist 44–54.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-06 — matching and driver onboarding

- **Owns:** checklist 55–60.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-07 — production driver PWA

- **Owns:** checklist 61–64.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-08 — governed reporting and pilot readiness

- **Owns:** checklist 65–68.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-09 — controlled pilot, training and handover

- **Owns:** checklist 69–71.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

### PKG-10 — admitted Cardvert audit remediation

- **Owns:** remediation slices R01–R60.
- **Contract:** [Detailed package criteria](delivery-contracts.md#package-contracts).

## Remediation slice register

The candidate IDs, direct dependency sets and checkpoint codes are immutable
admission data. Review receipts use the slice-bound forms `RNN-P`, `RNN-M` and
`RNN-CP-CODE`; a receipt in this register is an acceptance pointer, not proof by
assertion. The controller must inspect and record its supporting evidence in the
durable ledger before changing a row.

| Slice | Candidate IDs | Dependencies | State | Plan review | Diff review | Domain checkpoint |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | GOV-001 | none | COMPLETE | PASS — R01-P | PASS — R01-M | CP-CONTROL PASS — R01-CP-CONTROL |
| R02 | GOV-003, TST-001, DB-005 | R01, R04 | COMPLETE | PASS — R02-P | PASS — R02-M | CP-CONTROL PASS — R02-CP-CONTROL |
| R03 | GOV-004 | R02 | COMPLETE | PASS — R03-P | PASS — R03-M | CP-CONTROL PASS — R03-CP-CONTROL |
| R04 | DB-004 | none | COMPLETE | PASS — R04-P | PASS — R04-M | CP-DB PASS — R04-CP-DB |
| R05 | DB-001, TST-012, ONB-010 | R02, R04 | COMPLETE | PASS — R05-P | PASS — R05-M | CP-DB PASS — R05-CP-DB |
| R06 | DB-002 | R02, R04, R05 | COMPLETE | PASS — R06-P | PASS — R06-M | CP-DB PASS — R06-CP-DB |
| R07 | DB-003 | R02, R04, R06 | COMPLETE | PASS — R07-P | PASS — R07-M | CP-DB PASS — R07-CP-DB |
| R08 | GOV-005 | none | COMPLETE | PASS — R08-P | PASS — R08-M | CP-SECURITY PASS — R08-CP-SECURITY |
| R09 | GOV-007, AUT-001, AUT-002 | R10 | COMPLETE | PASS — R09-P | PASS — R09-M | CP-SECURITY PASS — R09-CP-SECURITY |
| R10 | AUT-005 | R08 | COMPLETE | PASS — R10-P | PASS — R10-M | CP-SECURITY PASS — R10-CP-SECURITY |
| R11 | AUT-004 | R09 | COMPLETE | PASS — R11-P | PASS — R11-M | CP-SECURITY PASS — R11-CP-SECURITY |
| R12 | AUT-003, REL-003 | R11 | COMPLETE | PASS — R12-P | PASS — R12-M | CP-SECURITY PASS — R12-CP-SECURITY |
| R13 | SEC-001, PRV-008 | none | COMPLETE | PASS — R13-P | PASS — R13-M | CP-PRIVACY PASS — R13-CP-PRIVACY |
| R14 | SEC-002, TST-004 | R12 | COMPLETE | PASS — R14-P | PASS — R14-M | CP-SECURITY PASS — R14-CP-SECURITY |
| R15 | GOV-006 | none | COMPLETE | PASS — R15-P | PASS — R15-M | CP-WORKERS PASS — R15-CP-WORKERS |
| R16 | GOV-008 | none | COMPLETE | PASS — R16-P | PASS — R16-M | CP-CONTROL PASS — R16-CP-CONTROL |
| R17 | TST-007 | R02, R03 | COMPLETE | PASS — R17-P | PASS — R17-M | CP-CONTROL PASS — R17-CP-CONTROL |
| R18 | MON-005, MON-006 | R04, R06, R07 | COMPLETE | PASS — R18-P | PASS — R18-M | CP-MONEY PASS — R18-CP-MONEY |
| R19 | MON-002 | R18 | COMPLETE | PASS — R19-P | PASS — R19-M | CP-MONEY PASS — R19-CP-MONEY |
| R20 | MON-001, DB-007, MON-008 | R05, R18 | COMPLETE | PASS — R20-P | PASS — R20-M | CP-MONEY PASS — R20-CP-MONEY |
| R21 | MON-003 | R20 | COMPLETE | PASS — R21-P | PASS — R21-M | CP-MONEY PASS — R21-CP-MONEY |
| R22 | MON-004, MON-007, MON-009 | R20, R21 | COMPLETE | PASS — R22-P | PASS — R22-M | CP-MONEY PASS — R22-CP-MONEY |
| R23 | COM-001, COM-004 | R08 | COMPLETE | PASS — R23-P | PASS — R23-M | CP-COMMERCIAL PASS — R23-CP-COMMERCIAL |
| R24 | COM-002 | R08, R23 | COMPLETE | PASS — R24-P | PASS — R24-M | CP-COMMERCIAL PASS — R24-CP-COMMERCIAL |
| R25 | COM-003, COM-005 | R08, R24 | COMPLETE | PASS — R25-P | PASS — R25-M | CP-COMMERCIAL PASS — R25-CP-COMMERCIAL |
| R26 | COM-006 | R08, R25 | COMPLETE | PASS — R26-P | PASS — R26-M | CP-COMMERCIAL PASS — R26-CP-COMMERCIAL |
| R27 | COM-007 | R08, R26 | COMPLETE | PASS — R27-P | PASS — R27-M | CP-COMMERCIAL PASS — R27-CP-COMMERCIAL |
| R28 | CAM-001 | none | COMPLETE | PASS — R28-P | PASS — R28-M | CP-CAMPAIGN PASS — R28-CP-CAMPAIGN |
| R29 | CAM-002 | R04, R08, R28 | COMPLETE | PASS — R29-P | PASS — R29-M | CP-CAMPAIGN PASS — R29-CP-CAMPAIGN |
| R30 | CAM-003 | R29 | COMPLETE | PASS — R30-P | PASS — R30-M | CP-CAMPAIGN PASS — R30-CP-CAMPAIGN |
| R31 | CAM-004 | R18, R19, R30 | COMPLETE | PASS — R31-P | PASS — R31-M | CP-CAMPAIGN PASS — R31-CP-CAMPAIGN |
| R32 | ONB-002 | none | COMPLETE | PASS — R32-P | PASS — R32-M | CP-ONBOARDING PASS — R32-CP-ONBOARDING |
| R33 | ONB-006 | R05, R32 | COMPLETE | PASS — R33-P | PASS — R33-M | CP-ONBOARDING PASS — R33-CP-ONBOARDING |
| R34 | OFF-001 | R04 | COMPLETE | PASS — R34-P | PASS — R34-M | CP-OFFLINE PASS — R34-CP-OFFLINE |
| R35 | OFF-002, OFF-003 | R34 | COMPLETE | PASS — R35-P | PASS — R35-M | CP-OFFLINE PASS — R35-CP-OFFLINE |
| R36 | OFF-005 | R35 | COMPLETE | PASS — R36-P | PASS — R36-M | CP-OFFLINE PASS — R36-CP-OFFLINE |
| R37 | OFF-006 | R36 | COMPLETE | PASS — R37-P | PASS — R37-M | CP-OFFLINE PASS — R37-CP-OFFLINE |
| R38 | PRV-001, PRV-002 | R13 | COMPLETE | PASS — R38-P | PASS — R38-M | CP-PRIVACY PASS — R38-CP-PRIVACY |
| R39 | PRV-003 | R38 | COMPLETE | PASS — R39-P | PASS — R39-M | CP-PRIVACY PASS — R39-CP-PRIVACY |
| R40 | PRV-004, AUD-001, AUD-002 | R16, R39 | COMPLETE | PASS — R40-P | PASS — R40-M | CP-PRIVACY PASS — R40-CP-PRIVACY |
| R41 | PRV-009, AUD-004, TST-010 | R40 | COMPLETE | PASS — R41-P | PASS — R41-M | CP-PRIVACY PASS — R41-CP-PRIVACY |
| R42 | PRV-005, PRV-006 | R41 | COMPLETE | PASS — R42-P | PASS — R42-M | CP-PRIVACY PASS — R42-CP-PRIVACY |
| R43 | PRV-007 | R42 | COMPLETE | PASS — R43-P | PASS — R43-M | CP-PRIVACY PASS — R43-CP-PRIVACY |
| R44 | AUD-005 | R16, R40 | COMPLETE | PASS — R44-P | PASS — R44-M | CP-PRIVACY PASS — R44-CP-PRIVACY |
| R45 | MET-003 | R04, R41 | COMPLETE | PASS — R45-P | PASS — R45-M | CP-REPORTING PASS — R45-CP-REPORTING |
| R46 | REP-001 | R45 | COMPLETE | PASS — R46-P | PASS — R46-M | CP-REPORTING PASS — R46-CP-REPORTING |
| R47 | MET-001, MET-002, MET-004, REP-002 | R41, R46 | COMPLETE | PASS — R47-P | PASS — R47-M | CP-REPORTING PASS — R47-CP-REPORTING |
| R48 | REP-003 | R47 | COMPLETE | PASS — R48-P | PASS — R48-M | CP-REPORTING PASS — R48-CP-REPORTING |
| R49 | REP-004 | R47, R48 | COMPLETE | PASS — R49-P | PASS — R49-M | CP-REPORTING PASS — R49-CP-REPORTING |
| R50 | REP-005 | R47, R49 | COMPLETE | PASS — R50-P | PASS — R50-M | CP-REPORTING PASS — R50-CP-REPORTING |
| R51 | REP-006 | R43, R49, R50 | COMPLETE | PASS — R51-P | PASS — R51-M | CP-REPORTING PASS — R51-CP-REPORTING |
| R52 | MET-006 | R51 | COMPLETE | PASS — R52-P | PASS — R52-M | CP-REPORTING PASS — R52-CP-REPORTING |
| R53 | REL-005 | none | COMPLETE | PASS — R53-P | PASS — R53-M | CP-RELEASE PASS — R53-CP-RELEASE |
| R54 | REL-006 | R12, R16, R53 | COMPLETE | PASS — R54-P | PASS — R54-M | CP-RELEASE PASS — R54-CP-RELEASE |
| R55 | REL-004 | R03, R18, R48, R51, R54 | COMPLETE | PASS — R55-P | PASS — R55-M | CP-RELEASE PASS — R55-CP-RELEASE |
| R56 | TST-005 | R09, R11, R14, R40 | COMPLETE | PASS — R56-P | PASS — R56-M | CP-SECURITY PASS — R56-CP-SECURITY |
| R57 | TST-008 | R19, R27, R49, R55 | COMPLETE | PASS — R57-P | PASS — R57-M | CP-RELEASE PASS — R57-CP-RELEASE |
| R58 | TST-011 | R15, R20, R21, R43, R49, R51 | COMPLETE | PASS — R58-P | PASS — R58-M | CP-WORKERS PASS — R58-CP-WORKERS |
| R59 | TST-002 | R22, R31, R33, R37, R41, R44, R48, R50, R51, R56, R57, R58 | COMPLETE | PASS — R59-P | PASS — R59-M | CP-RELEASE PASS — R59-CP-RELEASE |
| R60 | GOV-009 | R03, R17, R18, R22, R27, R31, R33, R37, R43, R44, R52, R55, R56, R59 | COMPLETE | PASS — R60-P | PASS — R60-M | CP-CONTROL PASS — R60-CP-CONTROL |

## Architecture traceability — non-executable parent groups

These 22 historical architecture groups are traceability only. They are not
packages, statuses, or review cycles and can never be promoted.

RM17's production-PWA/staging parallel intent is handled as disjoint internal work in
PKG-01 under its package plan; there are never two active packages.

| Order | Parent outcome | Type | Outcome and architectural authority | Prerequisites | Gate impact | Completion evidence required |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | **RISK-01 — production-PWA real-device proof** | PARENT | Android/iOS installable-PWA ADR and real-device proof for screen-on enforcement, permissions, visibility degradation, durable queue, tracking health, battery, reload/offline and session safety (§23, D18/RM17). Synthetic routes only. | Stable D15/D16 ping/seal contract **[BUILT]** | Produces early D18/RM17 evidence for **G-pilot**; authorises no real GPS | Browser/device matrix, measured SLO evidence, live synthetic-trip simulation, and independent review. |
| 2 | **RISK-02 — synthetic staging** | PARENT | Exercise the production-like topology with synthetic data before W2 grows it (§25, RM17). | Owner approval before external spend; Q32 blocks production, not preproduction work | Produces early RM17 evidence for **G-pilot**; authorises no live data | Deployment/recovery/smoke evidence or an explicit `BLOCKED` row naming the missing approval. |
| 3 | **W0-01 — stationary-time policy** | PARENT | Decide and implement RM2's sub-window rule (§16.1, §35 RM2; D2/D4/Q5). | Record the owner-approved money policy before code; obtaining it is part of this slice | Closes RM2's remaining contribution to **G-GPS** | Decision row; adversarial cases; payout integration + regression tests; independent money review. |
| 4 | **W0-02 — integrity conflict mapping** | PARENT | Map the four exclusivity constraint races to stable 409 envelopes (§6.4, §35 RM7). | W0-01 | Closes RM7 before pilot | Constraint tests and API envelopes; no unhandled `IntegrityError`. |
| 5 | **W0-03 — correction authority** | PARENT | Effective-dated immutable payout rules, correction orders, value-complete audit, and maker-checker approval (§16, §35 RM6). | W0-02 | Closes RM6's contribution to **G-money** | Migration/model/API/UI tests; historical-pricing and creator≠approver proofs; independent money/security review. |
| 6 | **W1-02 — fraud assessment, holds, disputes** | PARENT | Current per-trip assessment, authoritative non-terminal hold invariant, serialised review transitions, driver reasons/dispute, and minimal in-app notification (§17/§20, RM8; software controls from RM9). | W0-03; must precede S3 | Closes RM8's contribution to **G-money** and part of RM9 for **G-GPS** | State-transition, race, release-predicate, worker, API/UI, e2e, and independent money/concurrency review. |
| 7 | **W1-03A — release scheduling** | PARENT | Clean earnings release without a blanket delay; flagged earnings remain held under one RM8 predicate with a seven-day review SLA and no auto-release (§16.2, D18/Q22). | W1-02 | Satisfies the release-scheduling part of **G-money** | Time-boundary, escalation, no-auto-release, concurrency, retry, balance, worker, ops-UI tests, and independent money review. |
| 8 | **W1-03B — payout batches and reconciliation** | PARENT | Reservation/frozen payee/provider submission/line reconciliation plus carry-forward post-payment debt (§16.3, RM10/RM11, D18/Q27). | W1-03A + W0-03 | Closes RM10/RM11's contributions to **G-money** | Batch state-machine, uniqueness, instruction hash/idempotency, maker-checker, provider reconciliation, debt property tests, e2e, and independent money review. |
| 9 | **W2-00 — commercial money contracts** | PARENT | Advertiser company/profile management plus funded driver-liability authorization, effective-dated commercial terms, canonical receipt/allocation identity, audited production authority, cancellation cutoff/settlement, and atomic activation contracts (§15/§18/§21/§27, RM12/RM13, D20). | W1 complete | Defines how W2 closes RM12/RM13 for **G-commercial** | Reconciled design/invariants, migration plan, RBAC, concurrency/financial property tests, and independent architecture/money review. |
| 10 | **W2-01 — billing, invoices, payments** | PARENT | Per-campaign custom accepted terms, VAT-inclusive/itemised invoices, standard full-prepay plus approved-corporate credit, bank/gateway receipts, standard 24-hour production wait, audited expedited waiver, refunds and budgets (§15, D18/D20), built on W2-00. | W2-00; statutory company facts gate real issuance only | Partially closes **G-commercial**; real invoices remain blocked until company facts | Receipt dedup, amount/currency, webhook idempotency, invoice, production-authority/refund boundaries, budget, API/UI, e2e, and independent money review. |
| 11 | **W2-02 — secure files and KYC controls** | PARENT | Presigned storage, mandatory type/size/malware checks, purpose-scoped reads, encryption/key governance, and privileged-read audit (§12/§19, RM18). | Record storage/vendor decision before implementation | Closes RM18 for KYC/PWA pilot and contributes to **G-GPS/G-pilot** | Upload/download/security tests, audit evidence, retention/DSR coverage, and independent threat review. |
| 12 | **W2-03 — approvals, evidence, activation, cancellation** | PARENT | Campaign/creative/installation review; proof-of-display, device/vehicle binding, atomic activation, change requests, cancellation cutoff and settlement (§18/§19/§21, RM9/RM13). | W2-00/01/02 | Closes RM13 for **G-commercial** and remaining RM9 controls for **G-GPS** | Lifecycle/race tests, evidence review, cutoff clipping, settlement, API/UI, ops e2e, and independent review. |
| 13 | **W2-04 — notification and account-contact channels** | PARENT | Outbox-backed advertiser email and in-app triggers, password recovery, verified driver phone/consent; operations-run driver WhatsApp remains manual (§20/§23, Q34). | W1 notification core + W2 event sources | No independent gate; required MVP communication and recovery path | Retry/dedup/provider-receipt, token security, preference/consent, redaction, and user-flow tests. |
| 14 | **W3-00 — privacy and measurement foundation** | PARENT | DPIA/ROPA/roles/retention/DSR controls; central disclosure control; measurement methodology, immutable runs, uncertainty, proof-of-performance and the performance-report/conditional-ROI contract (§22/§24/§27, RM15/RM16, D20). | Qualified Nigerian legal/privacy review is required before live use, not before building controls | Closes RM15/RM16 contributions to **G-GPS/G-advertiser/G-moduleG** | Approved artefacts/runbooks, disclosure/differencing tests, reproducible performance and conditional-ROI fixtures, and independent privacy/measurement review. |
| 15 | **W3-01 — retargeting sources, segments, insights** | PARENT | Typed aggregate sources, campaign/zone linkage, exposure segments, controlled insights, export and gated geography/time/context activation with person-level payload rejection (§22, D6/D11/D18/D20/Q11). | W3-00; legal artifacts gate export and EXT-AD-PLATFORM gates live aggregate contextual activation | Implements **G-moduleG** subject to live-use gates | Privacy-boundary, provenance, suppression, schema rejection, export/activation approval, API/UI, e2e, and independent privacy review. |
| 16 | **W3-02 — exposure score and high zones** | PARENT | Versioned exposure metric and high-exposure zone views over reproducible measurement runs (§22.4/§27). | W3-00/01 | Implements the governed advertiser outputs behind **G-advertiser** | Formula fixtures, disclosure controls, reproducibility, report/UI tests, and independent measurement review. |
| 17 | **W3-03 — matching, offers, activity** | PARENT | Eligibility/scoring recommendations, admin assignment, driver offer response, inactive sweeps and flags (§21, Q7/Q20). | W2-03 activation/evidence | Required assignment/operations capability; no independent gate | Deterministic scoring, exclusivity/race, sweep, API/UI, and driver/admin e2e tests. |
| 18 | **W3-04 — driver self-registration and vehicle onboarding** | PARENT | Public application, secure document upload, bank/KYC and driver-owned vehicle-profile review before work (§23, Q13/Q23/Q26; proposal Module C). | W2-02 + W3-03 | Must preserve RM18 controls before KYC/vehicle use | Abuse/security, review-state, KYC/vehicle audit, API/UI, onboarding e2e, and independent security/privacy review. |
| 19 | **W4-01 — production driver PWA** | PARENT | Installable screen-on pilot client with fail-closed permissions/visibility, durable offline/retry sync, session safety, tracking health and the frozen backend contract (§23, D18). | RISK-01 + W1–W3 | Supplies the D18 PWA replacement for RM14's former native **G-pilot** gate and closes relevant RM15/RM18 contributions | Full Android/iOS browser/device matrix, battery/completeness SLOs, security review, and journey e2e. |
| 20 | **W4-02 — exports and issued reports** | PARENT | Remaining bounded CSV/PDF Campaign Performance Analysis package, with true ROI only behind the D20 data-and-method gate (§27/§30, D11/D20). | W3-00/01/02 | Governed by **G-advertiser/G-moduleG** | Performance/ROI golden files, access/privacy controls, reproducibility, load, UI tests, and independent privacy/measurement review. |
| 21 | **W4-03 — pilot deployment and readiness** | PARENT | Cardvert client-owned deployment, observability, restore/recovery, incident rehearsal, provider/permit gates and Abuja pilot acceptance (§25/§26, D18–D20/RM17). | All prior slices; registered external gates | Closes **G-pilot** only when every §35.3 gate passes | Staging burn-in, backup/restore, smoke/load/security evidence, provider/permit/legal approvals, and independent launch review. |
| 22 | **W4-04 — onboarding, training, handover** | PARENT | Role-based training, operator runbooks, support/handover and post-MVP roadmap promised by D11. | W4-03 release candidate | Final MVP delivery evidence, not a technical gate | Accepted materials, rehearsed operating flows, known-risk/deferment register. |

## Mandatory checklist item register

This register preserves the complete implementation detail from the reviewed
71-item decomposition. Each item belongs to exactly one package and remains a
binding acceptance obligation, but no row here is independently promoted or
requires a separate owner-facing review cycle. A checklist specification may
be refined inside its package without weakening its outcome, acceptance,
verification, gates or required specialist review.

| # | Checklist item | Package | Status | Observable outcome | Prerequisites |
| ---: | --- | --- | --- | --- | --- |
| 1 | **R14-A — production-PWA direction and protocol ADR** | PKG-01 | DONE | Executable evidence freezes installability, screen-on, permission, visibility, session, queue and seal semantics for the pilot PWA. | none |
| 2 | **R14-B — cross-profile interrupted-trip build proof** | PKG-01 | DONE | Desktop and mobile browser profiles prove the complete interrupted synthetic-trip contract; physical Android/iPhone route and battery runs remain deferred validation. | leaf: R14-A |
| 3 | **R17-A — production-like release/recovery build proof** | PKG-01 | DONE | Provider-neutral production-like topology, release smoke and recovery controls verify locally with synthetic data; external deployment remains deferred validation. | none |
| 4 | **FND-02A — stationary-time policy decision** | PKG-01 | DONE | Owner records a versionable rule separating traffic exposure from parked-time farming. | none |
| 5 | **FND-02B — stationary policy implementation** | PKG-01 | DONE | Classifier, fingerprints and earnings explanations implement the recorded rule. | leaf: FND-02A; external: EXT-RM2-POLICY |
| 6 | **FND-07 — exclusivity conflict envelopes** | PKG-01 | DONE | Four known assignment/trip races return stable 409 errors, not 500s. | none |
| 7 | **MNY-06A — immutable payout-rule revisions** | PKG-01 | DONE | Financial rule history becomes effective-dated, immutable and value-audited. | none |
| 8 | **MNY-06B — assignment/trip rule binding and payout_v3** | PKG-01 | DONE | Accepted driver terms freeze base/premium rates, zone/eligibility revisions and the `payout_v3` rule used by each interval/trip. | leaf: MNY-06A |
| 9 | **MNY-06C — maker-checker correction orders** | PKG-01 | DONE | Retroactive recompute requires a projected order and separate approver. | leaf: MNY-06B |
| 10 | **MNY-08A — current fraud assessments** | PKG-02 | DONE | Every sealed trip has one current pending/clean/flagged/error assessment. | none |
| 11 | **MNY-09A — cross-trip/account replay detection** | PKG-02 | DONE | Identical and time-shifted route replay becomes reviewable evidence. | leaf: MNY-08A |
| 12 | **MNY-08B — review states and hold invariant** | PKG-02 | DONE | One serialized transition table and hold predicate controls all money consumers. | leaf: MNY-08A, MNY-09A |
| 13 | **MNY-08C — driver reasons, disputes and in-app notice** | PKG-02 | DONE | Drivers can see holds, dispute them and receive sanitized outcomes. | leaf: MNY-08B |
| 14 | **MNY-03A — clean release and flagged review SLA** | PKG-02 | DONE | Clean entries release idempotently; flagged entries remain held for approve/decline with seven-day escalation and no auto-release. | leaf: MNY-08B |
| 15 | **MNY-10A — protected payee/account foundation** | PKG-02 | DONE | Payouts target an immutable payee and verified bank-account version safely. | none |
| 16 | **MNY-10B — batch reservation and provider submission** | PKG-02 | DONE | Available entries are atomically reserved into frozen, idempotent provider instructions and submitted only after maker-checker approval. | leaf: MNY-10A |
| 17 | **MNY-10C — provider line reconciliation and paid finality** | PKG-02 | DONE | Each automated transfer line reconciles from signed webhook/verified poll evidence before cash-paid finality. | leaf: MNY-10B |
| 18 | **MNY-11A — carry-forward post-payment debt** | PKG-02 | DONE | Later corrections reduce future pay without rewriting paid history. | leaf: MNY-10C, MNY-06C |
| 19 | **W2-00A — packages, custom quotes and accepted terms** | PKG-03 | DONE | A versioned custom quotation for every campaign—including an externally prepared quote recorded afterward—creates one immutable accepted snapshot; the legacy title does not authorize a launch package catalogue. | leaf: MNY-11A |
| 20 | **W2-00D — advertiser company profile management** | PKG-03 | DONE | Advertiser and admin manage tenant-safe company/contact details used by commercial surfaces. | none |
| 21 | **W2-00B — canonical receipts and allocations** | PKG-03 | DONE | One immutable external receipt can fund obligations once, within its amount. | leaf: W2-00A |
| 22 | **W2-01A — VAT-itemised invoices** | PKG-03 | DONE | Admin issues numbered immutable invoices; advertiser sees VAT-inclusive pricing with included net, VAT line and gross balance. | leaf: W2-00A, W2-00D |
| 23 | **W2-01B — manual bank-transfer confirmation** | PKG-03 | DONE | Ops reconciles transfers into the shared receipt/allocation/payment history. | leaf: W2-00B, W2-01A |
| 24 | **W2-00C — funded/approved-credit liability authorization** | PKG-03 | DONE | Standard work is fully prepaid and waits 24 hours before production; approved corporate credit remains bounded, while any expedited start requires an immutable advertiser waiver and audited actual start. | leaf: W2-01B, MNY-11A |
| 25 | **W2-01C — gateway adapter and webhook ingestion** | PKG-03 | BLOCKED — EXT-PAYMENT-PROVIDER | One-off Q3 checkout and signed provider events converge into canonical receipts. | leaf: W2-00B, W2-01A; external: EXT-PAYMENT-PROVIDER |
| 26 | **W2-01D — credits, reversals and 24-hour refund registry** | PKG-03 | DONE | Standard refund eligibility lasts to the 24-hour boundary; expedited eligibility ends only when production actually begins under an immutable advertiser-requested waiver. | leaf: W2-01A, W2-01B |
| 27 | **W2-01E — advertiser-spend budget enforcement** | PKG-03 | DONE | Spend facts drive persisted alerts/pauses without using driver payout cost as a proxy; live policy values remain externally gated. | leaf: W2-01A, W2-01B |
| 28 | **W2-02A — private object-storage foundation** | PKG-04 | DONE | Direct private uploads produce managed stored-file records; production adoption remains gated by EXT-STORAGE-PROVIDER. | none |
| 29 | **W2-02B — malware scanning and purpose-scoped reads** | PKG-04 | DONE | Unsafe files fail closed and privileged downloads are short-lived/audited; production adoption remains gated by EXT-MALWARE-SCANNER. | leaf: W2-02A |
| 30 | **W2-02C — advertiser creative upload** | PKG-04 | DONE | Campaign flows use managed scanned assets instead of arbitrary URLs; legacy URL rows remain readable but cannot authorize a new offer. | leaf: W2-02B |
| 31 | **W2-02D — encrypted KYC and financial identifiers** | PKG-04 | DONE | Required documents/NIN/bank data reuse the crypto port and are protected/version-reviewed; production custody remains gated by EXT-KMS-CUSTODY. | leaf: W2-02B, MNY-10A |
| 32 | **W2-02E — file/KYC lifecycle and incident operations** | PKG-04 | DONE | File/KYC purge plus scanner/key/vendor failures are tested and audited. | leaf: W2-02B, W2-02D |
| 33 | **W2-03A — campaign submission and approval** | PKG-04 | DONE | Advertiser submits; admin approves/rejects; unapproved campaigns cannot schedule. | none |
| 34 | **W2-03B — creative review gate** | PKG-04 | DONE | Only admin-approved, scan-cleared creative can satisfy campaign launch. | leaf: W2-02C |
| 35 | **W2-03C — installation evidence and proof-of-display** | PKG-04 | DONE | Assignment-bound evidence and nonce proof gate earning eligibility. | leaf: W2-02B |
| 36 | **W2-03D — atomic activation** | PKG-04 | DONE | One admin command locks/rechecks every commercial and operational prerequisite, including valid standard-wait or expedited-waiver production authority. | leaf: W2-00C, W2-01A, W2-01B, W2-03A, W2-03B, W2-03C |
| 37 | **W2-03E — governed mid-flight changes** | PKG-04 | DONE | Expansions honor funded headroom; reductions need approval and effective revisions. | leaf: W2-00A, W2-00C, W2-03D |
| 38 | **W2-03F — cancellation cutoff and settlement** | PKG-04 | DONE | One idempotent cutoff stops new work, clips pay and applies the standard-boundary or actual-waived-start refund rule. | leaf: W2-01D, W2-03D, MNY-11A |
| 39 | **W2-03G — proof challenges and spot checks** | PKG-04 | DONE | Missed challenges and physical verification feed the authoritative fraud hold. | leaf: MNY-09A, W2-03C, W2-03D |
| 40 | **W2-04A — notification core and role surfaces** | PKG-04 | DONE | W1 in-app notices become the shared outbox/list/unread-preference system. | leaf: MNY-08C |
| 41 | **W2-04B — advertiser email delivery** | PKG-04 | DONE | Worker-dispatched email and signed receipts update one logical notification; live delivery remains gated by EXT-EMAIL-PROVIDER. | leaf: W2-04A |
| 42 | **W2-04C — business triggers and manual driver contact** | PKG-04 | DONE | Stable event keys notify users; driver WhatsApp remains an audited ops task. | leaf: W2-04A, W2-04B, W2-01E, W2-03F, W2-03G, MNY-10C |
| 43 | **W2-04D — account recovery and verified contact preferences** | PKG-04 | DONE | Advertiser/admin password reset and driver verified-phone/WhatsApp consent are explicit; live pilot sends remain gated by EXT-PHONE-OPERATOR. | leaf: W2-04B, W2-04C |
| 44 | **W3-00A — privacy operating model** | PKG-05 | DONE | DPIA/ROPA/roles/lawful bases/consent/vendor/breach responsibilities are explicit. | none |
| 45 | **W3-00B — end-to-end retention and DSR** | PKG-05 | DONE | Synthetic DSR spans DB, objects, devices, logs, backups and processors. | leaf: W3-00A, W2-02E |
| 46 | **W3-00C — central disclosure-control service** | PKG-05 | DONE | Every advertiser heatmap/report/audience query enforces one privacy floor. | leaf: W3-00A |
| 47 | **W3-00D — measurement methodology contract** | PKG-05 | DONE | Product defines modelled potential contacts, provenance, uncertainty and claims; Campaign Performance Analysis is standard and true ROI requires approved inputs and method. | none |
| 48 | **W3-00E — immutable measurement runs and proof manifests** | PKG-05 | DONE | Issued results bind frozen inputs to creative/evidence/assignment/period and reproduce whether the ROI gate passed or failed closed. | leaf: W3-00D, W2-03C, W2-03D |
| 49 | **W3-01A — typed retargeting source registry** | PKG-05 | DONE | Advertiser/admin manage allowlisted aggregate planning sources without identifiers. | leaf: W3-00A, W3-00D |
| 50 | **W3-01B — source/campaign/zone linkage** | PKG-05 | DONE | Owned sources link safely to campaigns, zones and time windows. | leaf: W3-01A |
| 51 | **W3-01C — governed exposure segments** | PKG-05 | DONE | Worker materializes versioned, suppressed coverage-cell/time aggregates. | leaf: W3-00C, W3-00D, W3-00E, W3-01B |
| 52 | **W3-01D — recommendations, export and gated activation** | PKG-05 | DONE | Safe geography/time/context recommendations, controlled export and activation use one governed aggregate; identifiers/person-level payloads reject and live push fails closed without EXT-AD-PLATFORM. | leaf: W3-01C, W3-00D, W3-00E |
| 53 | **W3-02A — exposure score v1** | PKG-05 | DONE | Formula-versioned score is reproducible and distinct from impressions. | leaf: W3-00D, W3-00E |
| 54 | **W3-02B — high-exposure zone insights** | PKG-05 | DONE | Governed ranked zones appear in admin/advertiser maps and reports. | leaf: W3-00C, W3-00E |
| 55 | **W3-03A — matching recommendations** | PKG-06 | DONE | Admin receives deterministic eligible driver/vehicle rankings. | none |
| 56 | **W3-03B — complete offer lifecycle** | PKG-06 | DONE | Terms-complete expiring offers support accept/decline and immutable evidence. | leaf: W3-03A, W2-00A, MNY-06B |
| 57 | **W3-03C — activity floor and inactivity handling** | PKG-06 | DONE | Verified-hours/inactivity sweeps create reviewable ops flags and notices. | leaf: W3-03B, W2-04A |
| 58 | **W3-04A — public driver application** | PKG-06 | DONE | Abuse-resistant registration creates a pending, non-work-eligible application. | none |
| 59 | **W3-04B — KYC/bank onboarding approval** | PKG-06 | DONE | Person/payee KYC is approved but remains non-work-eligible pending W3-04C vehicle approval. | leaf: W3-04A, W2-02D, MNY-10A |
| 60 | **W3-04C — driver vehicle profile and approval** | PKG-06 | DONE | Identity/KYC-approved applicants add vehicle evidence; admin approval grants work eligibility. | leaf: W3-04B, W2-02B, W2-02D |
| 61 | **W4-01A — PWA foundation and session security** | PKG-07 | DONE | The installable production client uses the BFF session safely and fails closed on unsupported permission/storage/lock states. | leaf: R14-A, R14-B; external: EXT-PKG07-OWNER-RELEASE |
| 62 | **W4-01B — screen-on tracking and durable sync** | PKG-07 | DONE | Explicit Start/End tracking survives reload/network interruption, reports visibility degradation and never claims unsupported background capture. | leaf: W4-01A, R14-B |
| 63 | **W4-01C — PWA onboarding and campaign journey** | PKG-07 | DONE | Onboarding, vehicle, offers, activation and tracking integrate through governed BFF/API contracts. | leaf: W4-01B, W3-04C, W3-03B, W2-03D |
| 64 | **W4-01D — PWA earnings, disputes and release rehearsal** | PKG-07 | DONE | History, earnings, disputes, notifications, installability and production-PWA release evidence are complete. | leaf: W4-01C, MNY-08C, MNY-11A, W2-04A, W2-04C |
| 65 | **W4-02A — governed maps and report experience** | PKG-08 | DONE | Existing maps/reports consume safe runs; performance analysis is standard and ROI is absent unless its data/method gate passes. A production basemap remains a live-release gate, not a provider-neutral build prerequisite. | leaf: W3-00C, W3-00D, W3-00E, W3-01D, W3-02A, W3-02B |
| 66 | **W4-02B — bounded CSV/PDF issuance** | PKG-08 | DONE | Async hashed exports reproduce the frozen performance/conditional-ROI decision and honor privacy/legal gates. | leaf: W4-02A |
| 67 | **W4-03A — client-owned release environment** | PKG-08 | BLOCKED — EXT-RELEASE-ENV, EXT-STAGING-APPROVAL | Provider-neutral deployment/recovery preparation is exhausted; DONE still requires an approved account/domain hosting a hardened release candidate plus live staging recovery validation. | leaf: R17-A, W4-01D, W4-02B; external-live: EXT-RELEASE-ENV, EXT-STAGING-APPROVAL |
| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 | BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS | Synthetic acceptance machinery is complete; DONE still requires every §35 gate and the controlled Abuja journey, including approved providers, contextual activation, performance/conditional-ROI reporting, automated transfer, deployment and permit evidence. | leaf: W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS |
| 69 | **W4-04A — role-based onboarding and training** | PKG-09 | BLOCKED — EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-OPERATIONS-OWNER | Provider-neutral role-task and operator preparation is exhausted; DONE still requires rehearsal with approved users and the named operations owner against the release candidate. | leaf: W4-01D, W4-02B; external-live: EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-OPERATIONS-OWNER |
| 70 | **W4-03C — controlled pilot and stabilization** | PKG-09 | BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER | Provider-neutral telemetry, rollback, replay, incident and evidence preparation is exhausted; DONE still requires approved users to run a monitored controlled pilot. | leaf: W4-01D, W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER |
| 71 | **W4-04B — handover, support and roadmap closure** | PKG-09 | BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER, EXT-BRAND-APPROVAL | Provider-neutral handover, support and roadmap preparation is exhausted; DONE still requires named-owner acceptance, release/brand approval and credential handover after the controlled pilot. | leaf: W4-01D, W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER, EXT-BRAND-APPROVAL |

## Checklist item specifications

The complete scope, acceptance and verification criteria remain binding in [delivery-contracts.md](delivery-contracts.md#checklist-item-specifications). The statuses and dependencies above are the sole work queue.

#### R14-A — production-PWA direction and protocol ADR

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### R14-B — cross-profile interrupted-trip build proof

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### R17-A — production-like release/recovery build proof

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### FND-02A — stationary-time policy decision

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### FND-02B — stationary policy implementation

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### FND-07 — exclusivity conflict envelopes

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-06A — immutable payout-rule revisions

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-06B — assignment/trip rule binding and `payout_v3`

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-06C — maker-checker correction orders

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-08A — current fraud assessments

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-09A — cross-trip/account replay detection

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-08B — review states and hold invariant

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-08C — driver reasons, disputes and in-app notice

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-03A — clean release and flagged review SLA

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-10A — protected payee/account foundation

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-10B — batch reservation and provider submission

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-10C — provider line reconciliation and paid finality

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### MNY-11A — carry-forward post-payment debt

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-00A — packages, custom quotes and accepted terms

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-00D — advertiser company profile management

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-00B — canonical receipts and allocations

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-01A — VAT-itemised invoices

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-01B — manual bank-transfer confirmation

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-00C — funded liability authorization

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-01C — gateway adapter and webhook ingestion

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-01D — credits, reversals and 24-hour refund registry

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-01E — advertiser-spend budget enforcement

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-02A — private object-storage foundation

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-02B — malware scanning and purpose-scoped reads

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-02C — advertiser creative upload

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-02D — encrypted KYC and financial identifiers

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-02E — file/KYC lifecycle and incident operations

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03A — campaign submission and approval

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03B — creative review gate

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03C — installation evidence and proof-of-display

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03D — atomic activation

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03E — governed mid-flight changes

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03F — cancellation cutoff and settlement

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-03G — proof challenges and spot checks

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-04A — notification core and role surfaces

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-04B — advertiser email delivery

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-04C — business triggers and manual driver contact

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W2-04D — account recovery and verified contact preferences

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-00A — privacy operating model

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-00B — end-to-end retention and DSR

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-00C — central disclosure-control service

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-00D — measurement methodology contract

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-00E — immutable measurement runs and proof manifests

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-01A — typed retargeting source registry

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-01B — source/campaign/zone linkage

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-01C — governed exposure segments

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-01D — recommendations, export and gated activation

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-02A — exposure score v1

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-02B — high-exposure zone insights

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-03A — matching recommendations

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-03B — complete offer lifecycle

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-03C — activity floor and inactivity handling

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-04A — public driver application

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-04B — KYC/bank onboarding approval

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W3-04C — driver vehicle profile and approval

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-01A — PWA foundation and session security

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-01B — screen-on tracking and durable sync

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-01C — PWA onboarding and campaign journey

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-01D — PWA earnings, disputes and release rehearsal

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-02A — governed maps and report experience

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-02B — bounded CSV/PDF issuance

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-03A — client-owned release environment

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-03B — pilot gate and acceptance suite

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-04A — role-based onboarding and training

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-03C — controlled pilot and stabilization

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

#### W4-04B — handover, support and roadmap closure

- **Scope / authority:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Acceptance:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).
- **Verify / review:** [Detailed criterion](delivery-contracts.md#checklist-item-specifications).

## Coverage proof

The original requirement-to-checklist mapping remains in [delivery-contracts.md](delivery-contracts.md#coverage-proof); the 71-item register above controls status and dependencies.

## External prerequisite register

These stable IDs never disappear from the queue. `PRESENT` requires evidence;
`MISSING` blocks any checklist item that references the ID. Missing live-use
facts that are not build-entry prerequisites remain gates but do not block an
otherwise synthetic/provider-neutral checklist item or its package.

| ID | State | Input | Evidence | Needed by / exact effect |
| --- | --- | --- | --- | --- |
| **EXT-STAGING-APPROVAL** | MISSING | External staging provider/account/spend approval | — | Deferred external staging deployment/restore validation and later W4 release/pilot; D23 says it does not block R17-A's provider-neutral build proof |
| **EXT-RM2-POLICY** | PRESENT | Owner-approved RM2 stationary policy and parameters | `docs/decisions-log.md` D22; reviewed synthetic Option A | FND-02B implementation binds 120s/25m/2-confirm/1-release/per-trip values for new acceptances |
| **EXT-PAYMENT-PROVIDER** | MISSING | Payment provider sandbox/live authority, signing secret and public webhook endpoint | Existing Paystack test key verified locally on 2026-09-29; real ₦100 and ₦101 test checkouts initialized, and the ₦101 checkout completed, verified, processed and allocated once; localhost cannot prove provider webhook delivery | W2-01C remains blocked on public staging webhook/replay/recovery evidence, transfer evidence and production approval; provider refunds remain manual/unenabled |
| **EXT-STORAGE-PROVIDER** | MISSING | Production object-storage provider, account and region | — | W2-02A production adoption |
| **EXT-MALWARE-SCANNER** | MISSING | Malware scanner/provider | — | W2-02B fail-closed scan integration |
| **EXT-KMS-CUSTODY** | MISSING | KMS/vault and production key custodian | — | Production W2-02 controls; pilot interim is D17's typed-Settings-key envelope encryption through the shared crypto port |
| **EXT-EMAIL-PROVIDER** | MISSING | Email provider and verified sending identity | — | Live W2-04B delivery |
| **EXT-BUDGET-POLICY** | MISSING | Production budget alert/pause/resume values and approval | — | Live W2-01E policy adoption; configurable/provider-neutral implementation remains runnable |
| **EXT-PHONE-OPERATOR** | MISSING | Named phone-verification operator and approved manual WhatsApp/voice account | — | W2-04D pilot sends; generic challenge/consent tests remain synthetic |
| **EXT-BASEMAP** | MISSING | Production basemap provider/licence/account/API key | — | W4-02A live map release and W4-03B; public CARTO defaults remain development-only, while provider-neutral/local W4-02A build and tests remain runnable |
| **EXT-STORE-ASSETS** | MISSING | App Store and Play accounts/assets | — | Phase 2 native signing/listing only; not a PWA-pilot prerequisite |
| **EXT-RELEASE-ENV** | MISSING | Q32 client-owned account/domain, provider, budget and access action for Cardvert | — | W4-03A release environment; ownership direction and brand are confirmed, actual environment is absent |
| **EXT-PILOT-FACTS** | PRESENT | Abuja; 10 vehicles; 5 paying advertisers; 3 months; Campaign Performance Analysis, offline-to-online targeting and at least 60% target-area coverage; developer supports the initial pilot while training Somto operations | `docs/decisions-log.md` D18/D20, Q30/Q33 | W4-03B uses the confirmed cohort and performance-report goal; true ROI remains conditional on `EXT-REPORT-METHOD` inputs/method |
| **EXT-REPORT-METHOD** | MISSING | Client approval of impression-estimation methodology/labels and, for any true ROI output, the required conversion/revenue input schema plus reproducible attribution, cost-basis, time-window, exclusion and correction method | — | Performance-only contracts can build/test; first live issued report needs approved measurement method, and ROI remains omitted until its additional inputs/method are approved |
| **EXT-Q28-COMPANY** | MISSING | Terrax Media registered issuer name, TIN, address, invoice wording and accountant confirmation | — | VAT-inclusive display with itemised net/VAT/gross is confirmed; real W2-01A invoice issuance waits for these statutory facts |
| **EXT-COMMERCIAL-VALUES** | MISSING | Custom-quotation values/components, commissions, base/premium payout rates and production/vendor values | — | Real W2-00A/MNY-06 commercial use; schema remains configurable |
| **EXT-EVIDENCE-POLICY** | MISSING | Evidence uploader/views/renewal and RM9 challenge/spot-check thresholds | — | Pilot W2-03C/G enforcement |
| **EXT-LEGAL-PRIVACY** | MISSING | Q26/Q31 wording, privacy owner and retention/DSR decisions | — | KYC/live GPS/retargeting go-live |
| **EXT-DISBURSEMENT-PROVIDER** | MISSING | Approved automated bank-transfer provider, account, sandbox, signing/webhook credentials and production approval | — | Provider-neutral MNY-10B/C can build/test; financially effective submission and W4-03B cannot proceed |
| **EXT-AD-PLATFORM** | MISSING | Named ad-platform accounts, legal approval, API access/credentials and activation budget for aggregate geography/time/context activation | — | W3-01D can build/test provider-neutrally; any live aggregate contextual push remains disabled; person-level activation is outside the pilot |
| **EXT-PILOT-PERMITS** | MISSING | Abuja permit/authority evidence for the selected vehicles/campaigns | — | D19 assigns Terrax ownership and vendor coordination; W4-03B/launch remains blocked until evidence is approved |
| **EXT-PKG07-OWNER-RELEASE** | PRESENT | Explicit project-owner release to start Package 7 after this bounded Package 6 controller assignment | Project owner’s 25 Aug 2026 standing instruction to advance the next dependency-safe package automatically | W4-01A build admission is authorized; this is not a product or live-use prerequisite |
| **EXT-RM2-CALIBRATION-DATA** | MISSING | P1 parked-jitter and P2 Abuja-congestion field corpora (devices, participants, locations) per the owner-authorized 19 Aug 2026 Option-A collection program | — | Optional post-build calibration for a later effective revision; D22's reviewed synthetic selection is build-authoritative and this input blocks no checklist item |
| **EXT-BRAND-APPROVAL** | MISSING | Final Cardvert logo/brand asset pack and named client approver | — | Client-facing release assets and final handover acceptance; neutral development assets remain usable for build/test |
| **EXT-CAMPAIGN-BUDGET-SCOPE** | MISSING | Client decision on whether printing and other fixed costs consume the governed campaign budget | — | Production commercial configuration and acceptance; configurable synthetic budget enforcement remains runnable |
| **EXT-SETTLEMENT-BANK** | MISSING | Approved settlement bank-account details and custody/verification evidence | — | Live financial settlement only; no value is stored or invented before approved secure intake |
| **EXT-UPLOAD-POLICY** | MISSING | Client-approved file types and maximum sizes for each evidence/upload surface | — | Live upload policy adoption; existing fail-closed configurable limits remain build/test authority |
| **EXT-MESSAGE-COPY** | MISSING | Approved sender name and production email/WhatsApp/voice message copy | — | Live outbound communications; provider-neutral templates and delivery controls remain runnable |
| **EXT-RM2-APPROVER** | MISSING | Named client approver for any future RM2 calibration revision | — | Optional post-build RM2 revision only; D22 remains authoritative for current build and pilot preparation |
| **EXT-OPERATIONS-OWNER** | MISSING | Named receiving operations owner for Q33 training, pilot operations and handover | — | W4-04A/B rehearsal acceptance and operational handover; documentation/preparation remains runnable |

### Deferred post-build validation register

D23 keeps the following evidence visibly incomplete. These rows are not claims
that physical or external validation ran; they preserve the later gate and the
owner/action needed to run it.

| Validation | State | Deferred evidence | Required before |
| --- | --- | --- | --- |
| **DV-PWA-PHYSICAL-MATRIX** | NOT RUN — DEVICE ACCESS REQUIRED | Representative Android/iPhone installability, grant/denial/revocation, reload/offline/visibility/storage/lock behavior and completeness/sync-latency measurements | W4 production-PWA pilot acceptance / any real driver GPS |
| **DV-PWA-ROUTE-BATTERY** | NOT RUN — DEVICE/ROUTE ACCESS REQUIRED | Controlled real-route accuracy and four-hour battery measurement on the supported physical matrix | W4 production-PWA pilot acceptance |
| **DV-STAGING-LIVE** | NOT RUN — EXT-STAGING-APPROVAL | Deploy provider-neutral topology to an approved external environment; capture public-edge smoke, worker recovery, exact backup marker/revision restore and rollback evidence | W4 client-owned release and pilot gates |

Post-pilot work remains explicitly deferred: the native background driver app
and store distribution, expanded recurring billing, edge-AI vehicle/pedestrian
counting and multi-city optimisation (architecture §31). Automated driver
transfers are pilot scope. Aggregate geography/time/context ad-platform
activation is D18/D20 scope but stays fail-closed until `EXT-AD-PLATFORM` is
present; person-level activation is outside the pilot.


## Canonical repository

Use the active `mobility` checkout and its Git history for source and delivery evidence. Historical paths in [the archive](archive/progress-history-2026-09.md) are not current checkout instructions.

## Delivered so far

PKG-01, PKG-02, PKG-04–07 and PKG-10 are `DONE`. PKG-03 is blocked only at W2-01C; PKG-08 and PKG-09 await the named external and physical evidence. Built provider-neutral features do not authorize live payment, tracking, reporting, activation or deployment. The [package contracts](delivery-contracts.md) and architecture changelog carry implementation detail; Git and tests carry delivery proof.

## Where we are in the roadmap (architecture §31)

Provider-neutral implementation and synthetic preparation have reached the externally blocked frontier. The unfinished work is represented by the `BLOCKED` checklist rows above; Phase 2 native and post-pilot work stays deferred under D18 and architecture §31.

## Documentation authority

| Question | Source of truth |
| --- | --- |
| What the client wants now, by topic | [client-decisions.md](client-decisions.md), citing the formal D-rows and Q-rows in `docs/decisions-log.md` |
| Every request and its status | [requests.md](requests.md) |
| MVP scope and the formal decision record | `docs/decisions-log.md` D18 onwards and the client proposal where not superseded |
| Design and placement | `docs/architecture.md` |
| Which package/checkpoint may execute; statuses, dependencies and external gates | This file only |
| Binding package and checklist acceptance detail | [delivery-contracts.md](delivery-contracts.md), read with this file's status and execution lock |
| Historical receipts | [September delivery history](archive/progress-history-2026-09.md), earlier Git history and `docs/build-loop/` |
| Operations | `docs/runbook.md` |

## Update rules

1. Record every owner or client request in [requests.md](requests.md) before editing, as root `AGENTS.md` describes. It does not move this queue without explicit reprioritization.
2. For a package change, update this file's status, evidence and pointers, plus the live detailed criteria when needed. Keep external gates and deferred validation truthful.
3. Client product decisions land in `decisions-log.md` (formal record) and [client-decisions.md](client-decisions.md) (current rule and history by topic) in the same change; amend architecture only for a genuine design or product change.
4. A `DONE` claim requires every owned checklist item `DONE`, proportional deterministic and live/synthetic evidence, required review and applicable docs. Code alone is not completion.
5. Historical receipts may be archived after closure; live acceptance criteria remain editable in `delivery-contracts.md`. `docs/next-steps.md` and `docs/build-loop/` do not authorize work.
