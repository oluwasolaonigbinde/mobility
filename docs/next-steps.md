# Next Steps — W1 Remainder Slice Plan (S1–S4) + W2 Opener

**Audience: implementing agents.** This is the direction-level plan for the
next build slices, produced 27 Jul 2026 via the SOP (research → draft →
independent adversarial review → reconcile). It sequences the W1-remainder
work from `architecture.md` §31 and fixes the slice-level design decisions,
grounded in researched industry practice (anchors cited per slice).

**Precedence:** `architecture.md` > `adopted-decisions.md` > this plan. This
plan adds detail inside the architecture's fixed shapes; where it proposes an
architecture amendment, it says so explicitly and the implementing slice makes
that amendment in the same commit (amendment rule, architecture §1). If
implementation reality contradicts this plan, stop and flag — don't improvise.

## How to run a slice (binding on every implementing agent)

1. **Read first:** `architecture.md` §1/§30 (placement + amendment rule), the
   slice's referenced sections, `adopted-decisions.md` (statuses + divergence
   guards), and this plan's slice entry. Cite Q/D numbers in commits.
2. **Per-slice SOP:** this document is direction, not your implementation
   plan. Each slice still gets its own detailed implementation plan →
   independent fresh-context adversarial review → reconcile → implement
   (see memory SOP; the F7/worker slices are the quality bar).
3. **Gates:** full backend pytest (PostGIS+Redis services), frontend
   lint/typecheck/vitest/build, Playwright where surfaces change, contract
   discipline (§9: three baselines move per contract commit — `openapi.json`,
   `schema.d.ts`, `docs/api/openapi.snapshot.json`), migrations sequential
   from `0013` and frozen once shipped, live end-to-end verification against
   the compose stack (the worker slice's disposable-stack simulation is the
   model), `fablev1-work.md` build log updated per phase.
4. **Docs in the same commit:** architecture tag moves ([TARGET] → [BUILT]),
   `adopted-decisions.md` build-implication updates, changelog row, and any
   new decisions recorded in `decisions-log.md`.
5. **Settings discipline:** every tunable this plan marks `⚙` is a typed
   `Settings` field with the stated default — never a literal in code. Values
   that affect computed money are part of the computation fingerprint (S1).

## Sequencing

S1 → S2 → S3 strictly (S3 consumes S1's entries and S2's hold predicate).
S4 is independent of S1–S3 and pre-pilot-critical — run it in parallel in a
worktree if a second implementer is available, otherwise after S3. W2 opens
with S5 (billing) only after S1–S4 land.

Rationale (§31): every week built on `payout_v1` deepens the D2 rework, so the
hourly engine leads. Fraud review before release scheduling because the
release sweep consumes the hold predicate S2 defines (see S2/S3 for the
split). Partitioning is "before pilot", not "before S3" — the pilot date, not
the slice order, is its deadline.

## Ledger entry semantics (binding across S1–S3)

One sign convention, stated once so three slices cannot diverge on it:

- **All entry amounts are positive** — `ck_earnings_ledger_entries_amount_non_negative`
  (`app/models/payout.py:386`) forbids negatives and stays.
- **Downward money correction = partial `reversal` entry** (positive amount,
  reversal-typed). Per §16.2, every balance/summary computation **nets
  reversal-typed entries as negative** — and §16.2 mandates the netting ship
  **in the same change as the first reversal-creating code**. That is S1
  (recompute-day emits reversals), so **S1 ships the summary netting**
  (`driver_earnings_summary`, campaign cost summaries) with the property
  test "posting a reversal never increases any balance"; S3 re-verifies it
  at batch build.
- **Upward money correction = `adjustment` entry** (additive, e.g. freed-cap
  delta from a day true-up). Summaries treat adjustments as ordinary
  positive earnings; **no summary ever nets adjustments negative.**
- S1's recompute-day emits `adjustment` for upward deltas and partial
  `reversal` for downward deltas. S2's "adjust" review outcome is a partial
  reversal. S3's batch-build netting subtracts reversals only.
- No code today creates either entry type — S1 creates them first; if any
  slice needs different semantics, that is a §16.2 amendment and must be
  flagged as one.
- *Clarification (S1, 30 Jul 2026 — binding on S3):* the sign convention is
  per **balance**, not per status bucket: a differential entry inherits the
  corrected trip's `trip_payout` entry status (all `pending` until S3
  releases), so pending/available buckets net reversals negative within
  themselves; `voided_amount` stays an unsigned informational sum; campaign
  summaries net via a **separate** ledger aggregate (`ledger_net_total`)
  because differential entries carry no `payout_calculation_id` and never
  enter calc-joined sums.

---

## S1 — Payout engine v2: hourly pay + daily caps (D2, D4; Q4, Q5)

> **STATUS: DELIVERED 30 Jul 2026** (D9; architecture v1.7, §16.1 → [BUILT]).
> Built per this plan + its own reconciled implementation review. Notable
> reconciliations vs. the text below: v2 calculations are write-once per trip
> (input drift never auto-recomputes; recompute-day is the only corrective
> path), repair is rule-agnostic behind a one-trip_payout-per-trip DB guard,
> and the recompute-day admin UI panel was deferred (endpoint + tests shipped;
> frontend scope per this plan = editor + driver breakdown only).

**Architecture:** §16.1 (shape is fixed there — read it first). **Placement:**
`services/payouts.py` + `app/jobs/` per §30.

**Goal:** replace the transitional `payout_v1` stage in the trip pipeline with
the decided money model: `hourly_rate × verified payable time`, capped per
campaign/driver/Lagos-day, computed automatically on trip end.

### Design decisions (research-informed)

1. **Eligibility = classified interval timeline, not ping sampling.** Segment
   the session into contiguous intervals between consecutive pings; classify
   each with a reason code: `moving | stationary | gps_gap | out_of_area |
   out_of_window | teleport | low_accuracy`. Payable time = Σ durations of
   intervals passing **all** predicates. Persist `eligible_seconds` and
   `excluded_seconds_by_reason` (JSONB) per trip — this powers driver
   transparency (decision 8) for free. (Pattern: Uber/DoorDash/Prop-22 pay on
   classified intervals; nobody sums sampled pings.)
2. **Anti-time-farming is load-bearing, not optional** (risk R1; hourly pay
   maximizes the parked-with-screen-on incentive — the per-mile incumbents
   don't have this exposure). Stationary rule = stay-point detection: net
   displacement < ⚙ `PAYOUT_ELIGIBILITY_STATIONARY_RADIUS_M` (default 200)
   over a rolling ⚙ `PAYOUT_ELIGIBILITY_STATIONARY_WINDOW_MIN` (default 5)
   ⇒ `stationary` until real movement resumes — **with a grace period**: the
   first ⚙ `PAYOUT_ELIGIBILITY_STATIONARY_GRACE_MIN` minutes (default 4) of
   any stationary stretch still count (Lagos traffic is real; DoorDash
   counts merchant-wait the same way).
   Do not ship without the grace period — binary exclusion without it is the
   #1 boundary-dispute generator.
3. **Signal hygiene:** drop pings with reported horizontal accuracy worse
   than ⚙ `PAYOUT_ELIGIBILITY_MAX_ACCURACY_M` (default 75) → intervals become
   `low_accuracy`; interval speed (haversine/Δt) > ⚙
   `PAYOUT_ELIGIBILITY_TELEPORT_KMH` (default 180) → `teleport` (excluded AND
   counted as a fraud-engine input). Interval longer than ⚙
   `PAYOUT_ELIGIBILITY_MAX_PING_GAP_SECONDS` (default 120) → `gps_gap`,
   earns nothing, never interpolate across it (a gap is the cheapest spoof).
   Geofence rule is conservative: an interval is in-area only if **both**
   endpoint pings are inside the campaign area (position between pings is
   unknown). Clip intervals exactly at time-window boundaries (time is known
   precisely; space is not).

   **These knobs are NEW and payout-authoritative — they deliberately do NOT
   reuse the existing ingestion/analytics thresholds** in
   `app/core/config.py:66-75`, which stay untouched and keep their jobs:

   | New payout knob (money) | Existing knob (keeps its job) | Why different |
   |---|---|---|
   | `…_MAX_ACCURACY_M` 75 | `max_location_accuracy_m` 10000 (ingestion accept), `route_analytics_poor_accuracy_threshold_m` 100 (diagnostics) | pay demands tighter signal than storage/diagnostics |
   | `…_TELEPORT_KMH` 180 | `max_location_speed_mps` 120 (ingestion), `route_analytics_impossible_speed_mps` 55 (analytics flag) | ingestion keeps raw data; pay excludes it |
   | `…_MAX_PING_GAP_SECONDS` 120 | `route_analytics_max_ping_gap_seconds` 900 | analytics tolerates gaps; pay never pays across them |

   Consequence to embrace, not hide: `trip_analytics` active time (diagnostic)
   will read higher than payable time (money). **Driver-facing "verified
   time" always comes from the payout calculation, never from
   `trip_analytics`** — surfaces showing both must label them. The eligibility
   prefix keeps the two families grep-distinct.
4. **Time domain first, money once.** Keep payable time as **integer
   seconds** end-to-end. Cap truncation happens in seconds
   (`payable = min(eligible, cap_remaining)`), **before** pricing. Price once
   per ledger entry: `amount = rate × payable_seconds / 3600`, `Decimal`
   end-to-end, quantized to 2dp NGN at entry creation with
   ⚙ `ROUND_HALF_UP` (midpoint-neutral in expectation and the convention
   laypeople already know — chosen for explainability in driver-facing copy,
   not because it favors anyone; policy is frozen into `payout_v2` —
   changing it means `payout_v3`). Driver-visible
   day totals are **sums of posted entries, never re-derived**. Never round
   per-interval (drift), never cap after pricing (lost-kobo disputes).
5. **Lagos-day attribution per architecture:** a trip bills against the
   Africa/Lagos day its trip **started** (§16.1 — simpler than midnight
   splitting; the cap is a budget, not a shift rule). Use
   `zoneinfo("Africa/Lagos")`, never a hardcoded UTC+1. Cap concurrency =
   the sanctioned **advisory lock on (driver_profile_id, campaign_id,
   Lagos-day)** around the read-remaining-cap → write critical section.
   Mechanics (no advisory-lock code exists anywhere in the repo yet — S1
   builds the helper from scratch): **transaction-scoped
   `pg_advisory_xact_lock`** only (session-scoped locks leak across pooled
   asyncpg connections); lock key = first 8 bytes of
   `sha256(f"paycap:{driver_profile_id}:{campaign_id}:{lagos_date}")` as a
   signed bigint, derived in one shared helper so the pipeline stage and the
   recompute-day tool lock identically. Process a driver's same-day trips in
   deterministic order (trip start, then id) so recompute reproduces
   allocations. (Research preferred a locked `driver_campaign_day`
   accumulator row — rejected here under P10/§16.1 "no new table until
   measured cost says otherwise"; revisit only if cap discrepancies recur.)
6. **Voids on capped days — admin day-true-up, not auto-reallocation.**
   Architecture §16.1 forbids retroactive cap reallocation and says
   discrepancies are flagged for admin review. Ship the review tool with it:
   an admin **"recompute day"** action (extends the existing recompute
   endpoints) that re-runs the day's cap allocation under the advisory lock
   and emits **differential ledger entries per the sign convention above**
   (never edits): `adjustment` for upward deltas (freed cap), partial
   `reversal` for downward deltas — fully audited. This is the industry
   "period true-up" pattern (Prop-22 adjustment lines) made deliberate
   instead of automatic.
7. **Idempotency + staleness:** v2 calculations key on the natural unique
   constraint already used by the pipeline; store an **inputs fingerprint**
   (`sha256` over ping-set identity, rate, cap, eligibility params, geofence
   version, `formula_version`) on each calculation so staleness is detectable
   without recomputation — extends the existing source-fingerprint mechanism
   in `app/services/provenance.py` (used at `services/payouts.py:507`,
   `:964`); reuse it, don't fork it. "Geofence version" has no backing
   mechanism today (`campaign_zones` has no version column) — define it as
   `sha256` over the campaign's zone rows (ids + geometries + `updated_at`s),
   computed in the same helper, no schema change.
8. **Driver transparency (dispute prevention):** driver API exposes per trip
   `{eligible_seconds, excluded_seconds_by_reason, rate, capped_seconds,
   amount, entry_ids}`; the driver earnings screen renders rate × verified
   time = amount, excluded time by reason, and cap progress (D4 requires cap
   shown in the offer — keep the two consistent). Uber's trust drop when it
   hid time/distance breakdowns is the cautionary tale; our fixed rate is
   inherently explainable — lean into it.
9. **Min-floor loophole closes with v2** (§17): `min_payout_per_trip` floor
   applies only to trips with no open/confirmed flags. Record the policy in
   `decisions-log.md` (architecture notes it maps to no numbered question).

### Data model / migration (0013…)

Per §16.1, one migration: `campaign_payout_rules` gains nullable v2 fields
(`hourly_rate_naira`, `daily_payable_hours_cap`, eligibility params JSONB) +
**model XOR check** (v1 fields XOR v2 fields per rule row); relax v1 columns'
`NOT NULL` (existing rows frozen); `payout_calculations` **v1 component
columns go nullable — the `impression_estimate_id`/`trip_analytics_id` FKs
stay `NOT NULL`** (§16.1 mandates only the component-column relaxation; the
pipeline produces analytics + estimate before the payout stage in v2 too, so
v2 rows still link both — migration 0013 freezes once shipped, so do not
widen nullability speculatively); new columns for
`eligible_seconds`/`excluded_seconds_by_reason`/fingerprint if not derivable.
No new tables. Verify exact column names/constraints against
`app/models/payout.py` before writing the migration — the constraint names in
§16.1 are verified but the full column list lives in code.

**Rate resolution (Q4):** adopted Q4 specifies
`campaign.rate_override ?? platform.default_rate`. Implementation: the rule
row's `hourly_rate_naira` stores the **resolved** rate; the admin rules
editor prefills it from ⚙ `PAYOUT_DEFAULT_HOURLY_RATE_NGN` (Settings — no
platform-settings table exists and P10 forbids inventing one for a single
scalar). This satisfies Q4's divergence guard (single-rate-always = every
rule keeps the prefill) with one honest narrowing: the platform default is
config, not data, until the client needs runtime editing — record that
narrowing in `decisions-log.md` in the S1 commit.

### Scope

- Backend: eligibility classifier (pure, unit-testable function over pings),
  `payout_v2` computation in `services/payouts.py`, pipeline stage swap in
  `app/jobs/trip_processing.py` (v2 selected by the rule row's model),
  admin recompute-day endpoint, driver trip-breakdown endpoint, audit events
  on all new mutations (§6.4.9 — mandatory).
- **Named rework, not a "swap":** due-work/staleness/repair logic is
  currently keyed on the single global `settings.payout_formula_version`
  (`app/services/trip_processing.py:127`, `:433`). With per-rule model
  selection, v1 and v2 coexist across campaigns — the sweep's missing/stale
  predicates and `repair_missing_ledger_entries` must derive the **expected
  formula version from the governing rule row**, or the sweep will
  perpetually re-queue every trip whose rule model differs from the global
  setting. Budget this as its own work item with its own tests.
- Frontend: admin payout-rules editor refactored to edit either model
  ([BUILT] F6 editor — refactor, don't fork); driver earnings screen
  breakdown + cap progress.
- Contract: new/changed endpoints move the three baselines.

### Non-goals

No holds/release changes (S2/S3), no map-matching (OSRM noted as future
anti-fraud upgrade only), no per-driver rate negotiation (Q4 adopted: standard
rate + campaign override), no v1 row rewrites ever.

### Tests / verification

Unit: classifier edge cases (gap at session edge, teleport sandwich,
stationary-with-grace crossing a window boundary, both-endpoints geofence
rule, accuracy filter); money (rounding at 2dp, cap-truncate-then-price,
sum-of-entries invariant); Lagos-day attribution (trip starting 23:50).
Property test: Σ(eligible + excluded-by-reason) == session duration.
Concurrency: two same-day trips computed in parallel never jointly exceed the
cap (advisory-lock test, like the worker slice's admin-race test). Pipeline:
end-to-end trip → v2 entry on the disposable stack; recompute idempotency
(same fingerprint ⇒ no-op; changed param ⇒ flagged stale). Regression: v1
history rows still render in reports.

### Done criteria

Worker produces `payout_v2` calculations + ledger entries for trips under a
v2 rule with zero admin action; v1 paths untouched and green; driver can see
the breakdown; architecture §16.1 → [BUILT]; adopted-decisions Q4/Q5 rows
note delivery.

**Research anchors:** [Uber CatchME](https://www.uber.com/us/en/blog/mapping-accuracy-with-catchme/) ·
[DoorDash Earn by Time](https://dasher.doordash.com/en-us/blog/earn-by-time-mode-explained) ·
[Modern Treasury — ledger corrections](https://www.moderntreasury.com/journal/enforcing-immutability-in-your-double-entry-ledger) ·
[Fowler — Money allocation](https://martinfowler.com/eaaCatalog/money.html) ·
stay-point detection literature (distance+time threshold).

---

## S2 — Fraud review workflow + minimal in-app notifications (D5; Q21, Q34-subset)

**Architecture:** §17 (review lifecycle) + §20.1 (outbox/notifications —
in-app subset only). **Placement:** fraud modules + `services/notifications.py`
per §30.

**Goal:** turn the read-only fraud console into a working hold-and-review
queue with a driver dispute channel, carried by the platform's first
notification slice (in-app only; channel adapters are W2).

### Design decisions (research-informed)

1. **Flag lifecycle per §17, extended:** existing statuses
   (`open | acknowledged | dismissed`) + migration adds terminal `confirmed`,
   `reviewed_by_user_id`, `reviewed_at`, `resolution_note`, and **fixes the
   dedup-trap** (§17: unique index only guards `status='open'` — extend the
   predicate or detection-side check in the same migration, or re-detection
   duplicates every reviewed flag).
2. **Holds are bounded, never indefinite** (posture amendment — every mature
   platform bounds holds; indefinite withheld pay is regulator bait, cf. the
   NY AG's $328M Uber/Lyft settlement). Defaults, all ⚙ configurable:
   low/medium-severity flags **auto-expire** after
   ⚙ `FLAG_AUTO_RELEASE_DAYS` (default 7 — deliberately matches the T+7
   release window) — a worker sweep dismisses them with actor `system`,
   audited, and any held earnings release at the next release sweep
   (medium sits exactly at the default hold threshold, so this clause does
   real work; low-severity flags never hold at all). High-severity flags
   (the top of the code's low/medium/high scale — there is no `critical`)
   **never auto-release**; instead the sweep **auto-escalates** (re-notify
   admin + SLA-breach view) after ⚙ `FLAG_ESCALATION_DAYS` (default 3).
   Update `adopted-decisions.md` Q21 and architecture §17 with this policy in
   the slice commit; record in `decisions-log.md`.
3. **Review outcomes are three, not two:** release (dismiss), **adjust**
   (partial — confirm flag + post a **partial `reversal`** for the
   confiscated delta per the plan-wide sign convention; S1's recompute-day
   tool is the calculator when the right delta is "re-run eligibility"),
   void (confirm + full reversal). Real GPS anomalies are frequently
   partial; all-or-nothing voiding inflates disputes.
4. **Driver disclosure = category + observable fact, never thresholds.**
   "Speed pattern inconsistent with road travel on the 14:05 session" — not
   the km/h rule that triggered it (threshold disclosure teaches spoofers;
   Uber's carve-out, Santa Clara Principles' "sufficient to understand").
   Reason templates live in code per flag type.
5. **Dispute = one structured re-review request, no threads:** driver picks a
   structured reason + free text (photo attachment deferred to §19 files —
   don't build upload here), creating a dispute row linked to the flag,
   `open → resolved(upheld | overturned | adjusted)`. One dispute per flag;
   re-dispute blocked after denial. Outcome notification is **mandatory** and
   states decision + amount + category reason (post-appeal silence is the #1
   platform complaint).
6. **Assignment pausing stays recommendation-first** (§17 rules; research's
   auto-pause ladder rejected at pilot scale — false-positive rate of a
   fresh rules engine is unknown): a sweep surfaces "pause recommended"
   (high-severity flag, or ⚙ `K` held sessions in a rolling window) in the admin
   queue; pausing is an admin action; **un-pause is automatic** when the
   deciding flags resolve in the driver's favor. Track from day one:
   dispute overturn rate and flag→confirmation rate (they tell you when
   thresholds are miscalibrated — and whether auto-actions can ever be
   trusted).
7. **Notifications per §20.1's shape, in-app subset:** `notifications` table
   exactly as §20.1 specifies (dedupe_key unique-nullable, payload JSONB,
   channel enum with only `in_app` exercised, `provider_message_id` present
   but unused) plus `read_at timestamptz` (not boolean). Creation is
   `INSERT … ON CONFLICT DO NOTHING` on the dedupe key, **in the same
   transaction as the triggering mutation**; conflict = success (worker
   retries must not double-notify; dedupe key = business event id, never
   attempt number). Types are Python StrEnum + code template registry
   rendering at read time — no Postgres enum, no CMS. In-app dispatch is a
   no-op (the row is the notification).
8. **Feed API:** `GET /notifications` with the platform's standard
   `{items, total, limit, offset}` envelope — **limit/offset, not cursors**
   (§6.4.3 is a built invariant: "No cursors"; research's keyset suggestion
   is rejected to keep the contract uniform) — plus
   `GET /notifications/unread-count` (partial index `WHERE read_at IS NULL`),
   polled via TanStack Query at 30–60s; idempotent mark-read/mark-all-read.
   No unread-count denormalization at pilot scale — noted as a later
   optimization only. **S2 is the first slice to introduce TanStack Query —
   it must establish the shared QueryClient provider + conventions §27.2
   specifies in this PR**, not a page-local one-off.
9. **First notification types:** `earning_held`, `flag_escalated` (admin),
   `dispute_resolved`, `payout_batch_paid` (S3 emits it), `assignment_offer`
   (reserved — W3). In-app rows insert with channel-status `sent` (the row
   itself is delivery; §20.1's `pending→sent→delivered` ladder is for
   provider channels in W2). `flag_escalated` fans out as one row per active
   admin-role user (pilot admin count is single digits; no routing table).
   Every money-affecting review action writes an audit row
   in the same transaction with reason_code + note mandatory at write time
   (admin UI must not allow void/adjust without them), amounts before/after,
   flag + dispute ids. Test: from audit rows alone, reconstruct who decided,
   when, on what evidence, what changed, what the driver was told.

### Data model / migration

Fraud: status enum extension + review columns + dedup index predicate fix.
New tables: `notifications`, `fraud_disputes`. **`fraud_disputes` is an
explicit architecture amendment** — §17 says "free-text driver response
recorded against the flag" and "Replace: nothing"; a structured dispute row
(status machine, one-per-flag constraint, resolution fields) exceeds that.
Amend §17 + add the §30 placement row in the S2 commit per the amendment
rule; the alternative (columns on the flag row) was rejected because dispute
lifecycle ≠ flag lifecycle and the audit reconstruction test needs the
distinct actor trail.

**Hold semantics — S2 defines, S3 activates:** S2 ships the predicate as a
named function in `services/` (entry is releasable iff its trip has no
non-terminal flag at severity ≥ ⚙ `FLAG_HOLD_SEVERITY_THRESHOLD`, default
`medium` — medium/high count as "seriously flagged" per Q21/D5; low never
holds) with its own unit tests. No
ledger status changes in S2: entries post `pending` today
(`services/payouts.py:773`) and nothing sets `available` until S3's sweep
exists, so in the S2-only interim **every entry is effectively held anyway**
— coherent, and worth stating in the release-notes line of the PR. S3's
sweep imports this function; it does not redefine it.

### Scope

Backend: review endpoints (`/admin/fraud-flags/{id}/review` — acknowledge,
resolve w/ outcome), dispute endpoints (driver create, admin resolve),
notification service + feed endpoints, escalation/auto-expiry sweep job.
Frontend: admin fraud queue (acknowledge/resolve/outcome + SLA-breach view +
pause recommendations), driver flagged-trip visibility + dispute form,
notification badge + list on all three role surfaces.

### Non-goals

No email/SMS/WhatsApp adapters (W2), no auto-suspension, no file-upload
evidence on disputes (needs §19), no threading, no fraud-detection-engine
changes (extend flags, never the detector — §17 "Preserve").

### Tests / verification

Notification idempotency under job retry (dedupe conflict = success);
transactional co-commit (mutation rolls back ⇒ no notification); feed
pagination + unread count; flag lifecycle transitions incl. dedup-after-review
regression; auto-expiry sweep with frozen clock; dispute single-round
enforcement; audit completeness reconstruction test; Playwright: admin
reviews a held flag → driver sees outcome notification.

### Done criteria

A flagged trip can be reviewed, disputed, and resolved end-to-end with every
party notified in-app and every decision auditable, and the hold predicate is
built, tested, and ready for S3's sweep to consume (hold *behavior* becomes
observable only once S3 releases unheld entries); §17 → [BUILT], §20.1 →
[BUILT] (in-app subset tagged as such); Q21/Q34 rows updated.

**Research anchors:** [DoorDash under-review deliveries](https://help.doordash.com/en-us/dashers/article/dasher-under-review-deliveries) ·
[Upwork auto-release windows](https://support.upwork.com/hc/en-us/articles/211063748-How-Fixed-Price-Payment-Protection-works-for-freelancers-on-Upwork) ·
[NY AG settlement](https://ag.ny.gov/press-release/2023/attorney-general-james-secures-328-million-uber-and-lyft-taking-earnings-drivers) ·
[EU P2B statement-of-reasons](https://eur-lex.europa.eu/eli/reg/2019/1150/oj/eng) ·
[transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) ·
[Brandur — idempotency keys](https://brandur.org/idempotency-keys).

---

## S3 — Release scheduling + payout batches + runs UI (Q22, Q23, Q27)

**Architecture:** §16.2 (release + reversal netting) + §16.3 (batches, payee
abstraction). **Placement:** `jobs/` + `services/payouts.py` +
`adapters/disbursement/` port per §30.

**Goal:** pending earnings clear after the review window and flow into
weekly, immutable, exportable payout batches that ops can execute as manual
bank transfers and reconcile per line.

### Design decisions (research-informed)

1. **Release sweep (§16.2):** worker cron moves `pending → available` for
   entries past ⚙ `RELEASE_WINDOW_DAYS` (default 7) **with no open flags
   above the hold threshold** (S2's predicate) on their trip. Weekly batch
   anchor ⚙ `PAYOUT_BATCH_WEEKDAY` (default Friday). Cutoff semantic =
   **cleared-by-cutoff** (Stripe/Uber/DoorDash shape): the batch takes
   entries `available` at batch creation; an entry clearing mid-cycle waits
   for the next batch. State the resulting max time-to-pay
   (≈ 7 + ≤7 days + transfer) in driver-facing copy.
2. **Reversal netting arrived in S1** (shipped with the first
   reversal-creating change per §16.2's same-change mandate — see the
   plan-wide ledger block). S3's job: **re-verify** the netting property
   tests still pass over batch-build summation and extend them to the batch
   totals (a batch line's amount and the batch totals must reflect
   reversal-netted balances).
3. **Batch model (§16.3):** `payout_batches` (period_key, cutoff_ts, status
   `open → locked → processing → paid → reconciled`, + `void` pre-processing,
   totals, created_by) + line items that **snapshot amount, breakdown, payee
   display data, and bank details at lock time** (later profile edits must
   not alter a locked batch). Ledger `paid` status arrives by migration
   extending `ck_earnings_ledger_entries_status`; an entry is `paid` iff its
   completed batch line carries a transfer reference. **Batches are immutable
   once locked** — late discoveries post to the next open batch, never
   restate a locked one (this is what makes the exported CSV reconcilable).
4. **Payee abstraction is mandatory (Q23 no-rework promise):** lines attach
   to a `payee` reference (type + id), at pilot always the driver profile.
   No `driver_profile_id` assumptions in disbursement code paths.
5. **Idempotent weekly creation:** derive `period_key` from the schedule
   (ISO week whose cutoff most recently passed), never from wall-clock
   observation; `UNIQUE (period_key)` + `INSERT … ON CONFLICT DO NOTHING`
   is the guarantee (arq cron uniqueness is best-effort only — documented
   multi-worker race); attach lines with status-guarded UPDATE in the same
   transaction; refuse future cutoffs; **backfill missed weeks** (loop from
   last existing period forward) so a worker outage yields a late batch, not
   a skipped one.
6. **Negative nets carry forward:** at batch build, sum each payee's
   available entries **netting reversal-typed entries negative and nothing
   else** (plan-wide sign convention; adjustments are additive); if ≤ 0,
   **exclude from the batch and carry forward** (manual transfers cannot
   pull money back; never emit a negative payout line — §16.2: offsets
   future earnings, never a collections flow).
7. **Per-line reconciliation, not all-or-nothing:** lines go
   `pending_payment → paid(payment_reference, paid_at, marked_by) |
   failed(reason)`; batch status derives from its lines; bulk
   "mark remaining paid with shared reference" for the happy path, stored
   per-line regardless. `payment_reference` required (NIP session id or
   generated reference; audited "no reference" escape hatch), unique per
   line. Failed lines regenerate into the next open batch — never edited.
8. **Two export artifacts per batch:** (a) bank-ready bulk CSV with the
   column superset Paystack/Flutterwave bulk transfers accept
   (`beneficiary_name, bank_name, bank_code, account_number(NUBAN),
   amount_ngn, narration, reference`) — the `reference` column becomes the
   API idempotency key verbatim when Q27's automated fast-follow lands;
   (b) ops/audit PDF (period, per-payee breakdown, totals, carried-forward
   exclusions, generated-by/at). Narration convention:
   `"Vantage payout {batch_code}"` (working name per Q29).
9. **Bank-account capture dependency:** lines need verified driver bank
   details (Q26/Q27 adopted). If driver bank-account fields don't exist yet
   when S3 starts, S3 adds the minimal columns + admin-verified capture flow
   (per §30's bank-account row; BVN explicitly deferred to the automated
   fast-follow — do not collect it for manual transfers). A payee with a
   positive net but **missing/unverified bank details is excluded from the
   batch and carried forward** (same mechanics as decision 6), with an
   admin notification naming the blocked payee — never block the whole
   batch lock on one payee's paperwork.

### Data model / migration

`payout_batches` + `payout_batch_line_items` (payee-typed), ledger status
check-constraint extension (`paid`), driver bank-account columns if absent.

### Scope

Backend: release sweep job, batch-create job, batch/line endpoints, exports
(CSV + PDF), notification triggers (`payout_batch_paid` via S2's service),
audit on every adjustment/mark-paid. Frontend: admin payout-runs UI (create →
review → lock → export → mark-paid → reconcile), driver earnings screen shows
pending/available/paid states + batch history.

### Non-goals

No gateway-executed transfers (Paystack Transfers is the Q27 fast-follow
behind `adapters/disbursement/` — build the port interface, not the
adapter), no BVN collection, no per-campaign release-policy overrides (P10:
Settings until asked), no invoice/billing coupling (W2).

### Tests / verification

Release sweep: frozen-clock window math, hold predicate blocks release,
post-release flag → reversal recommendation path (§16.2). Netting property
tests across `driver_earnings_summary` + campaign cost summaries. Batch:
period_key idempotency under concurrent/duplicate cron fire, missed-week
backfill, lock immutability (post-lock adjustment lands in next batch),
negative-net exclusion + carry-forward, per-line state machine, CSV column
snapshot test. E2E on disposable stack: trip → v2 entry → clears at T+7 →
Friday batch → export → mark paid → driver notified + sees `paid`.

### Done criteria

Money flows trip → verified hourly earning → cleared → batched → exported →
reconciled with zero manual computation and a complete audit trail;
§16.2/§16.3 → [BUILT] (manual channel; adapter port defined); Q22/Q27/Q23
rows updated.

**Research anchors:** [Stripe payout schedule/balance lifecycle](https://docs.stripe.com/payouts) ·
[Paystack bulk transfers](https://paystack.com/docs/transfers/bulk-transfers/) ·
[Flutterwave bulk transfer](https://developer.flutterwave.com/v3.0/reference/create-bulk-transfer) ·
[Modern Treasury — immutability](https://www.moderntreasury.com/journal/enforcing-immutability-in-your-double-entry-ledger) ·
[arq #196 — cron uniqueness race](https://github.com/samuelcolvin/arq/issues/196).

---

## S4 — Data lifecycle: ping partitioning + retention + audit backfill (Q31-param; §24.2, §6.4.9)

> **STATUS: DELIVERED 3 Aug 2026** (D10; architecture v1.9, §24.2 → [BUILT]).
> Built per this plan + its own reconciled implementation review. Notable
> reconciliations vs. the text below: the migration is a single-transaction
> blocking conversion (env.py wraps upgrades in one transaction — the
> NOT VALID→VALIDATE split is kept for the ATTACH-no-scan property, not
> onlineness); the empty-DB branch also premakes three prior months (the
> rich seed writes 56 days of history; caught in the live drill); the
> in-migration premake horizon is frozen
> at 4 (never reads Settings); purge evidence is append-only lifecycle-EVENT
> rows (no detached_at/dropped_at updates); ping-batch ingestion is an
> approved audit exemption with `location_ping_batches` as compensating
> evidence; coverage alarm = worker Sentry check + `GET
> /api/v1/health/partitions`; residual pre-existing audit gaps and
> model↔migration index drift outside S4's scope are registered in the new
> tests as KNOWN lists, not silently blessed.

**Architecture:** §24.2 (design is fixed there) + §6.4.9 (audit honesty
note). **Placement:** migration + `jobs/` per §30. Independent of S1–S3;
pre-pilot deadline.

**Goal:** `location_pings` partitioned monthly so retention is `DROP
PARTITION`; configurable NDPR retention enforced by a worker job with an
audit-grade purge trail; the three unaudited endpoint groups backfilled.

### Design decisions (research-informed)

1. **Conversion = rename-and-attach, one Alembic migration** (`op.execute`
   raw SQL — no declarative support): add a `NOT VALID` CHECK covering the
   existing rows' time range → `VALIDATE` (only `SHARE UPDATE EXCLUSIVE`) →
   in one transaction rename `location_pings` → `…_legacy`, create the
   partitioned parent **matching `app/models/trip.py` exactly** — there is
   NO sequence (PK is UUID, default `gen_random_uuid()`, `trip.py:198-201`);
   recreate ALL of: column defaults, the seven CHECK constraints
   (`trip.py:166-191`), **both** FKs (`trip_session_id → trip_sessions` AND
   `batch_id → location_ping_batches`, NOT NULL + CASCADE,
   `trip.py:203-210`), and parent-level indexes → create current + future
   partitions → `ATTACH` legacy as a bounded partition (no scan — the
   validated CHECK matches) → drop the temp CHECK. Dropping any of these
   silently breaks model/DB parity and this slice's own "autogenerate emits
   empty diff" test. Set `lock_timeout` (2–5s) + `statement_timeout` in the
   migration so it fails fast rather than queueing behind traffic. At our
   scale skip the later legacy-split; the legacy partition ages out via
   retention. (Copy-migrate/pgslice rejected: earns its complexity only at
   volumes we don't have.)
2. **PK must include the partition key:** `id` alone cannot remain PK on the
   parent — composite PK `(id, recorded_at)`. The partition column is
   **`recorded_at`** (`trip.py:211`) — §24.2's `captured_at` is stale;
   amend it in the S4 commit per the amendment rule. **The ORM model must
   gain the same composite PK** in the same change, and every
   `session.get(LocationPing, …)` / single-column lookup must be swept and
   updated (record the sweep output) — otherwise the "autogenerate emits
   empty diff" gate fails or runtime lookups break. **Pre-flight sweep
   (record output in the slice plan): find any FK referencing
   `location_pings`** — each must be dropped/converted to a plain indexed
   column (ping rows are leaf data; an FK at them also blocks DETACH).
   Expected result: none — pings reference `location_ping_batches`, not the
   reverse (`trip.py:207-210`) — but verify, don't assume.
3. **No default partition** — it would make `DETACH … CONCURRENTLY` illegal
   and add a scan tax on every ATTACH. Instead: **premake job** (arq cron,
   daily, idempotent `CREATE TABLE IF NOT EXISTS … PARTITION OF`) keeps
   partitions existing through now + ⚙ `PARTITION_PREMAKE_MONTHS` (default
   4); an independent check (worker health path) asserts a partition covers
   `now() + 1 month` and alarms otherwise — the failure mode it prevents is
   a hard write outage on the hottest table (`no partition of relation found
   for row`). Naming `location_pings_pYYYY_MM`; read bounds from
   `pg_partition_tree`, don't parse names.
4. **pg_partman rejected** at this scale (extension install burden on
   managed Postgres, its own default-partition conventions conflict with
   decision 3; we already run arq cron — steal its premake/retention
   conventions, ~20 lines of SQL we fully control).
5. **Alembic autogenerate guard in the same commit:** `include_object`
   filter in `env.py` excluding `location_pings_p%`/`…_legacy` — without it
   the next autogenerate emits `drop_table` for every runtime-created
   partition.
6. **Retention job** (arq cron, daily, advisory-locked): cutoff = now −
   ⚙ `PING_RETENTION_MONTHS` (default 12, [OPEN] Q31 param); for each
   partition with upper bound ≤ cutoff: write the purge-audit row **before**
   the irreversible step → `DETACH … CONCURRENTLY` (autocommit — cannot run
   in a transaction; run `FINALIZE` first if a prior detach was interrupted)
   → `DROP`. After partition drops, purge `location_ping_batches` rows that
   have **zero remaining pings** (`NOT EXISTS`, not a time predicate —
   batches are keyed by `received_at` while partitions drop by
   `recorded_at`, and the pings' `batch_id` FK is CASCADE, so deleting a
   straddling batch by time-window would silently delete retained pings in
   newer partitions). **§24.2's "null trip_sessions coordinate columns"
   step: pre-flight-verify it — `TripSession` (`app/models/trip.py:44-114`)
   has no geometry/coordinate columns today** (only `location_pings.geom`
   exists, migration 0007), so the expected outcome is *nothing to null*;
   §7.1/§24.2.1's claims are stale vs code — amend both (and §24.2.1's
   cross-cite of "§22.2.1 precise start/end Point geometry") in the S4
   commit rather than inventing columns to satisfy them. `started_at`/
   `ended_at` timestamps stay untouched — they are not location data and
   the retention obligation covers coordinates, not session existence. Aggregates
   (`trip_analytics`, `impression_estimates`) are already computed at trip
   close by the pipeline and are retained indefinitely — purge is purely
   destructive, never on the analytics path.
7. **Purge audit = the NDPA/NDPR compliance artifact:** append-only
   `data_purge_audit` rows (partition, range, row count, retention config in
   force, initiator, detached_at/dropped_at, job run id) — the NDPA 2023
   requires demonstrable destruction practice and annual audit filings; an
   interrupted run honestly shows "detached, not dropped". **This table is
   an explicit architecture amendment** — §24.2.4 says "an audit event
   records the purge run"; a dedicated table (write-before-drop ordering,
   detached/dropped two-phase honesty, no envelope reuse) exceeds that.
   Amend §24.2.4 + add the §30 placement row in the S4 commit; rejected
   alternative: reusing `audit_events` couples the compliance artifact to
   the operational audit trail's retention and shape. Note in the backup
   runbook (§24.2.5): backup rotation ≤ 35 days so purged pings age out of
   backups.
8. **Audit backfill (§6.4.9):** trip start/end (`api/v1/trips.py`),
   analytics recompute (`api/v1/trip_analytics.py`), traffic/impression
   flows (`api/v1/impressions.py`) get `create_audit_event` calls — sweep
   the modules, don't spot-fix; add the regression test that every mutating
   route writes an audit event (route-table-driven, so new omissions fail).

### Non-goals

No heatmap precomputation (sanctioned fix only if p95 > 2s — measure first),
no pg_partman, no DSR automation (manual runbook per §24.2.6), no
`trip_sessions` partitioning.

### Tests / verification

Migration on a seeded prod-like DB (legacy rows present): conversion
preserves counts/ids/FKs, inserts route to partitions, autogenerate emits
empty diff post-filter. Premake idempotency; missing-partition alarm fires
when premake is disabled in a test stack. Retention with frozen clock:
partition past window detaches+drops, audit row written first, aggregates
and `trip_sessions` rows survive, straddling ping-batches keep their newer
pings (zero-remaining-pings purge predicate), `FINALIZE` recovery path. Heatmap
endpoints still green over partitioned table (GiST per-partition). Full
pytest suite green — the migration chain from empty DB to head must pass
(worker slice bar).

### Done criteria

Purge = partition drop with compliance evidence; write outage impossible via
premake+alarm; every mutating route audited; §24.2 → [BUILT], §6.4.9 honesty
note deleted; runbook updated.

**Research anchors:** [Postgres ddl-partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) ·
[AWS rename-and-attach walkthrough](https://aws.amazon.com/blogs/database/partition-existing-tables-using-native-commands-in-amazon-rds-for-postgresql-and-amazon-aurora-postgresql/) ·
[ALTER TABLE — DETACH CONCURRENTLY/FINALIZE constraints](https://www.postgresql.org/docs/current/sql-altertable.html) ·
[Crunchy — default-partition tax](https://www.crunchydata.com/blog/postgres-partitioning-with-a-default-partition) ·
[NDPR Implementation Framework](https://nitda.gov.ng/wp-content/uploads/2021/01/NDPR-Implementation-Framework.pdf).

---

## S5 — W2 opener: billing, invoices, payments (Q1–Q3, Q14, Q28) — SKETCH ONLY

Not specced here; gets its own plan after S1–S4. Fixed by §15 + adopted
decisions: invoices + N-payments-per-invoice shape (§15.2), funding status
from `invoices.status` (§15.3) feeding the Q15 activation gate, both manual
bank-transfer confirmation and gateway webhooks (`payment_events` with
provider-unique replay protection), configurable VAT defaulting VAT-exclusive
(Q28 mechanism; placeholder company facts until Somto answers), packages as
admin data (Q1), invoice generation only — quotations stay manual (Q14).
Sequencing note: S5 before file storage (§19) and approval workflows (§18)
per §31's W2 ordering; §20's email channel adapter lands in W2 alongside
(advertiser comms per Q34).

## Open parameters (all ⚙ Settings; defaults ship, client can retune)

All S1 eligibility knobs carry the `PAYOUT_ELIGIBILITY_` prefix (see S1
decision 3's mapping table for how they relate to the pre-existing
ingestion/analytics thresholds, which are untouched).

| Setting | Default | Slice | In money fingerprint? |
|---|---|---|---|
| PAYOUT_ELIGIBILITY_STATIONARY_RADIUS_M / \_WINDOW_MIN / \_GRACE_MIN | 200 m / 5 min / 4 min | S1 | yes |
| PAYOUT_ELIGIBILITY_MAX_ACCURACY_M / \_TELEPORT_KMH / \_MAX_PING_GAP_SECONDS | 75 / 180 / 120 | S1 | yes |
| PAYOUT_DEFAULT_HOURLY_RATE_NGN (admin-editor prefill, Q4) | set pre-pilot | S1 | resolved rate is on the rule row |
| ROUND mode | HALF_UP (frozen in payout_v2) | S1 | via formula_version |
| FLAG_HOLD_SEVERITY_THRESHOLD (hold predicate) | medium | S2 | no |
| FLAG_AUTO_RELEASE_DAYS / FLAG_ESCALATION_DAYS | 7 / 3 | S2 | no |
| Pause-recommendation K-in-window | 3 held in 14 d | S2 | no |
| RELEASE_WINDOW_DAYS / PAYOUT_BATCH_WEEKDAY | 7 / Friday | S3 | no |
| PING_RETENTION_MONTHS / PARTITION_PREMAKE_MONTHS | 12 / 4 | S4 | no |

If Somto's answers land mid-flight and contradict an adopted default, stop,
record the superseding row in `decisions-log.md`, and re-plan the affected
slice (divergence guards in `adopted-decisions.md` were designed to make this
cheap — use them).
