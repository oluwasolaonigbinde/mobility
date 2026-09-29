# September 2026 Delivery History

Historical receipts and superseded status summaries moved from [progress.md](../progress.md) on 29 Sep 2026. They are evidence and context, not execution authority.

### Current control pointer

**Controller state:** `PAUSED — EXT-PAYMENT-PROVIDER`
**Control package:** `PKG-03` — all provider-neutral commercial work is complete;
the remaining payment-provider checkpoint requires registered external authority.
**Current checkpoint:** `PKG-03 / W2-01C` — PKG-10 remediation is complete. R02 is accepted at `09c0b17`, R47 at
`419414a`, R03 at `60af07d`, R48 at `b17d1e7`, R05 at `954d9a4`, R49 at
`a315a59`, R33 at `14f155a`, R06 at `05b4901`, R07 at `84cb94e`, and R50 at
`bb8c13e`, R18 at `5c2d60a`, R19 at `3c7b678`, R51 at `2f52c3e`, and R31 at
`eb59a84`, R52 at `cab745c`, R20 at `d8cd891`, R21 at `ee43b10`, R22 at `7835ba8`, R55 at `662077a`, R57 at `2599b87`, corrected R58 at `0c1d525`, R59 at
`fcba0dc`, R17 at `c78b5dc`, and terminal R60 at `fc0cb3a`.
AUT-006 is accepted at
`a4c9de2`.
Every repository failure group
discovered by R02's complete 1,772-test authority run is now accepted: V11
historical migration fixtures, V12 signed-v2 payout fixtures, V13 reversal
deadlocks, V14 trip-end/enqueue lifecycle and the controller-state correction.
R54 is accepted. R39→R44 plus D30 are accepted as one integrated privacy/audit
chain with migrations 0075–0077. R29→R30 is accepted at `32d617f` and R45 at
`7f7bd1c`; R56 is accepted at `751060c`. R02's exact CI-authority patch now also
provisions the application Redis URL, `jq`, lockfile-pinned frontend dependencies and
Playwright Chromium; focused checks and an immutable frontend-image build are green.
Both Opus correction packets are accepted at `aa7ff02` and `bce94ad`, and R46
is accepted at `1c89f16`. R02's complete immutable run and focused complement are
preserved, but the focused W403B browser journey exposed a real trip-end protocol
failure now owned by R36→R37; R02 will resume only after that packet is accepted.
R36→R37 is accepted with migration 0080, signed mixed-batch disposition and
server-owned grace-expiry adjudication. R02's final W403B approval-aware correction
is accepted at `09c0b17`: the composed immutable authority is 2,541 passing
executions with zero skips, and R02-M, DB+DEP and R02-CP-CONTROL all pass. R47 is
accepted at `419414a` with complete caveated measurement facts, source/calibration
provenance, frozen ROI methodology and screen/CSV/PDF parity; R47-M and
R47-CP-REPORTING pass. Its released contract lane promoted R03 and its reporting
dependency promoted R48; both are accepted. R05 is accepted at `954d9a4`,
releasing the exclusive database lane to R06 while accepted R49 promotes R50 on
its disjoint report-reissue lease. The owner has now selected R17 Option A;
R17 planning is ready, while implementation waits for R59 to release the
central CI workflow lease.

CI-throughput continuation (12 Sep 2026): run `34690115628` on `2a3f7e0` failed before pytest because Docker Hub denied the existing MinIO image on all six runners; backend static verification and quality passed and the aggregate failed closed. R59 failed at the same MinIO pull, confirmed in its failed log. Both original cached MinIO/MC index digests match Quay exactly (`d249d1fb6966de4d8ad26c04754b545205ff15a62e4fd19ebd0f26fa5baacbc0` / `fb8f773eac8ef9d6da0486d5dec2f42f219358bcb8de579d1623d518c9ebd4cc`), verified by image inspection and successful digest pulls. Reviewed bounded correction pulls those identical digests explicitly and retags locally before unchanged backend and R59 startup; no script/product/Compose/version change or fallback. Pull-order regression observed red before correction then green; 79 shard/authority contracts PASS. Fresh exact-SHA CI and measured backend wall time remain mandatory.


## Direct owner requests outside the package queue

**Cardvert next build pass, Batches A–F (25 Sep 2026):** The owner directs the
build list in section 3 of the 25 Sep three-way action list, as decided in
D38 and D39 and the client answer register
(`issues/planning/client-answers-2026-09-24.md`), on the local `master`
baseline `edcda6b` (not pushed). This is a bounded direct-owner programme
outside the executable queue: the controller stays
`PAUSED — EXT-PAYMENT-PROVIDER`, no package is promoted or reordered, and no
live-use gate changes. Batches run in dependency order: A, D38 product fixes
plus budget alerts at 80/95/100 %, the installation-photo policy values and
per-purpose upload limits; B, the `payout_v4` daily-rate engine; C, automatic
payout approval with safeguards (depends on B); D, Paystack payment and
transfer adapters built from the public API documentation and tested against
recorded fixtures only; E, in-app complaints with a Customer Service inbox;
F, invoice layout, deployment environment templates, the client guide and
architecture §16 / PRD §7 amendments. Open client parameters (shortfall
formula, which miles count, the 70-mile cap, ₦10,000 or ₦9,800, payout
frequency, RC or TIN) are fail-closed configuration and are never invented;
`payout_v1`–`v3` earnings and accepted work are never repriced (D14/D21). The
Paystack password in the client document is never recorded or used; adapters
read keys from settings only and stay disabled without them. `PKG-03 / W2-01C`
resumes on the normal package path only when the owner supplies test keys.
Single writer: this Claude Opus 5.5 session; reviewers are read-only
clean-context subagents. Gates per batch: one independent plan review, one
post-build review to `PASS`, D32 changed-line coverage against `edcda6b`
(≥90 % lines, ≥80 % branches) and a live check on the `cardvertmain` stack
(ports 3001/8001); Batches B and C also get money and security specialist
reviews. No commit, push, deployment, provider call or external-account action
is authorized without separate owner approval. Batch records follow below as
each batch closes.

Batch A record (25–26 Sep 2026, uncommitted working tree on `edcda6b`).
Scope: D38(a)–(e), budget alerts at 80/95/100 %, the client photo policy and
per-purpose upload limits. Plan review (read-only Opus 5.5 stand-in) returned
6 material and 8 minor findings, all adopted: vehicle evidence keeps PDF
papers; no invented "externally approved" budget values on the live stack;
the client's "fixed costs count toward the budget" is deferred to a money
batch (G-21 stays open); money and security specialist reviews added; the
driver keeps every accepted term in readable words ("Full job terms") and
loses only the fingerprint and raw JSON; the E2E campaign flow (dates, a
target area, new review text) and admin headings updated; a fixed
item-to-endpoint table for the admin queue with a per-item "Couldn't check";
two-level budget evaluation keys unchanged.

Delivered. D38(a): signed-in copy names Terrax Media when a person acts and
reads "Nigeria time (WAT)", including the budget, evidence and activity
notices. D38(b): `/driver/capabilities` is a plain Phone check (five yes/no
rows, fixes, "Copy for support"); the unchanged R14-A probe is the unlinked
`?view=support`. D38(c): hashes, run IDs and fingerprints are removed from
advertiser and driver screens (staff screens and downloads keep them).
D38(d): `submit_campaign_for_review` refuses a campaign without start/end
dates, a positive total budget or a target zone (409
`CAMPAIGN_INCOMPLETE_FOR_REVIEW`, `details.missing`, nothing written); the
campaign page lists what is missing and the wizard states the rule. D38(e):
the admin home is "Waiting for you", grouped by Operations, Compliance,
Finance, Customer Service and Admin over existing list endpoints. Budget:
migration `0091` adds the urgent level (`urgent_threshold_amount`, state
`urgent_threshold`), `BUDGET_URGENT_RATIO` joins the complete fail-closed
set, and warning/urgent/pause notices also reach active admins in the app;
all budget values stay blank in every template (policy revision and resume
ratio not supplied). Photo policy: front, back, left, right, close-up; driver
or admin; 168 h in the release templates; the driver policy endpoint no
longer waits for the separate, still-open display-proof windows. Uploads:
identity documents 10 MB; vehicle documents and photos 20 MB; installation
photos 20 MB; artwork 25 MB; types per purpose; report exports refused;
client-side checks match. OpenAPI, snapshot and TypeScript baselines moved
together.

Specialist reviews: money (A6) `PASS`, security (A8, A2, A7, D38(c)/(d))
`PASS`, both Opus 5.5 stand-ins; their low findings adopted (frontend upload
checks, settings-wiring test, E2E location count). Residuals recorded: a
campaign budget under about ₦0.10 whose thresholds round together stops that
budget-sweep run (pre-existing, fail-closed); upload confirmation does not
recheck the new policy for intents created before deploy. EXT-UPLOAD-POLICY
and EXT-EVIDENCE-POLICY register rows are unchanged: the owner should confirm
the upload recommendation with the client, and display-proof and spot-check
values remain open.

Evidence (26 Sep 2026). Backend: `ruff check` passes; the 30 files that
exercise the changed code ran under coverage (889 passed; the 12 failures are
all in `test_w403a_release_preparation.py` and environmental: no `docker`
binary in the test image and CRLF shell scripts on the Windows checkout; its
environment-template parity tests, which cover `BUDGET_URGENT_RATIO`, pass).
A local full-suite run in three shards completed two shards: 804 passed / 25
failed and 1,342 passed / 33 failed + 6 errors. Every failure there is
environmental (no `docker` or `npm` in the test image; CRLF shell scripts on
the Windows checkout) except nine: seven pass when rerun alone (load-sensitive
lock and copy tests) and two fail identically on `edcda6b`
(`test_evidence_verification::test_satisfied_challenge_stays_satisfied_after_assignment_cancellation`,
`test_migration_payout_downgrade_guards::test_0014_concurrent_insert_is_serialized_before_downgrade_guard`).
The third shard was stopped under the owner's 26 Sep instruction to leave the
full suite to GitHub CI (6 Linux shards) after an approved push and run only
the touched files locally (contract amendment R17); that CI run remains an
open gate. Changed E2E specs ran in a local Playwright container: the campaign
submission and approval journey and the admin work queue pass; the journey's
cleanup step and the cookieless session probe need `docker` and host
networking that the container lacks, and the advertiser dashboard check
expects results that this stack's default privacy configuration hides.
Migration `0091` upgrade, downgrade and refusal are tested; the local
`cardvertmain` database is at `0091`. Frontend: `tsc`,
ESLint and Prettier on the changed files pass; the full Vitest suite passes
162 files / 1,044 tests, including the R14-B fixtures. OpenAPI `--check`
passes after moving `openapi.json`, the snapshot and `schema.d.ts` together.
D32 changed lines against `edcda6b` from local LCOV: backend 53/53 lines and
20/20 branches; frontend 233/243 lines (95.9 %) and 160/181 branches
(88.4 %). The first exact-SHA CI run after an approved push must refresh the
D33 baseline for the new files. Live on `cardvertmain` (3001/8001, local
override adding the photo policy only): admin "Waiting for you" with real
counts; wizard and edit labels in WAT; a new name-only draft lists what is
missing and Submit returns the plain refusal (status stays draft); no hashes
on campaign, report or jobs screens; "Budget alerts: Not set up yet"; the
driver Phone check ran real probes (storage and sign-in yes; wake lock and
location refused by the desktop pane, with fixes shown); the support view
keeps the probe; the jobs page shows the five photo views without a
display-proof prompt; Track links "Phone check". The urgent level and admin
notices are proven by service tests with synthetic authority, not on the live
stack. During the run Docker Desktop stopped responding under memory load and
was restarted; every container that had been running was started again, except
another project's auto-removed `tss-test-runner` run container. Nothing is
committed or pushed.

Batch B record (26–27 Sep 2026, uncommitted worktree `batch-b` on `7a9ceb0`).
Scope: the D39 `payout_v4` daily-rate engine under the plan-reviewed contract
(Opus 5.5 stand-in; 7 material and 5 minor findings adopted before build).
Deviation from D39's "same batch" wording, as the owner's handoff directs:
architecture §16 gains a [BUILT] v4 paragraph and changelog row v1.98, while
the §16/PRD §7 rewrite and the client guide stay in Batch F.

Delivered. Migration `0092`: a rate-less `payout_v4` rule branch, v4
revision/binding terms (day rate, target miles, shortfall strategy with its
deduction, minimum miles, outside-area share) with per-formula shape checks
that refuse NULL values, per-day `distance_m_by_day`/`amount_by_day` on
calculations; downgrade refuses while any v4 row exists. Every pay value is a
required field of an audited revision; nothing is defaulted.
`PAYOUT_V4_PUBLISHING_ENABLED` (false in every template, because a blank
boolean does not parse; same fail-closed effect) returns 503
`PAYOUT_V4_POLICY_UNAVAILABLE` and writes nothing until the client answers
D39 Q1–Q3. New admin endpoints publish a revision (audited before/after, and
the rate-less rule when the campaign has none active) and report whether
publishing is on. Offers freeze and acceptance binds the exact values with the
server-fixed `d39-stop-5min-v1` stop rule (stays up to 300 s count as driving;
longer stays are excluded whole; no rolling detector, no whole-trip grace).
Distance is slice-prorated haversine metres, target zones in full and other
miles at the frozen share, exact per Lagos day and floored to whole metres;
pings buffered before Start add nothing. Each trip earns
`D(before + this) − D(before)` per day under the v2/v3 paycap locks and
predecessor gate; a day never mixes hourly and daily-rate pay (409 both
ways). Recompute-day re-measures the corrected day in start order and keeps
other days; executed correction orders record each daily-rate trip's
position even when the money delta is zero. Liability reservations and window
extensions reserve one day rate per covered day
(`day-rate-vehicle-days-v1`); the worker sweep never requeues v4 rows. The
admin "Daily rate" form and table (loading, empty, not switched on,
validation, retry, labelled inputs), the driver's plain "Pay and job terms"
sentences and the per-day trip breakdown are built. v1–v3 pricing is
unchanged.

Reviews: money specialist (Opus 5.5 stand-in) FIX → PASS after two rounds
(pre-start ping distance, then fractional-timestamp proration; a zero-delta
correction losing a re-measured distance); security specialist (Opus 5.5
stand-in) PASS. Its low note (an admin may retire an hourly rule and move a
campaign to daily rate) is kept as intended: the contract expects drivers with
earlier hourly work to take daily-rate offers, and same-day mixes are refused.
Residuals: the cross-campaign per-driver-per-day ceiling (Batch C); a voided
or later-held earlier trip shifts later trips only through a day correction;
parked GPS jitter under 5 minutes is credited (109 m for a 4-minute parked stop on a ±5 m synthetic trace); the retired
direct recompute path records a daily-rate position only with a money delta.

Evidence (27 Sep 2026). Backend: `ruff check` passes; the 25 test files that
exercise the change ran under coverage in five sequential chunks (a first
single run was lost when Docker Desktop crashed under memory load; every
previously running container was restarted except another project's
`tss-test-runner` database). 303 + 508 passed; chunk 5's 14 failures are the
12 environmental `test_w403a` failures seen in Batch A, the pre-existing
`test_0014` failure, and a real migration-head expectation, fixed and re-run
green with the architecture inventory regenerated. After the money fixes the
v4, correction, eligibility and dependent suites pass (nine files under coverage: 207 passed, plus the new fail-closed tests). D32 changed
lines against `7a9ceb0`: backend 460/488 lines (94.3 %) and 136/164 branches (82.9 %); frontend 84/85 lines (98.8 %)
and 127/144 branches (88.2 %). Frontend: `tsc`, ESLint and Prettier clean; the
full Vitest suite passes 163 files / 1,055 tests including the R14-B fixtures
(new admin action/page and driver offer tests added afterwards pass). OpenAPI
`--check` passes with `openapi.json`, the snapshot and `schema.d.ts` moved
together. Live check: the worktree API on port 8011 against a separate
`mobility_live_b` database (migrated to `0092`, demo seed, publishing on only
there; web and ClamAV not started to spare memory, so screens are proven by
Vitest). Through the real API: a revision without a deduction was refused
(422), a synthetic revision (₦3,000 day, 4 mi, ₦500 per missing mile, half
weight outside) was published (201) with the fixed stop rule, an offer froze
those terms with `d39-stop-5min-v1`, and the driver accepted. The demo
creative was given a synthetic clean file record in that database because
MinIO and ClamAV were stopped. Three synthetic sealed trips then ran the real
pipeline: 5,404 m → ₦2,678.94; 5,404 m → ₦321.06 (the day reaches exactly
₦3,000); the cross-midnight trip added ₦0.00 on the capped 15 Sep and
4,683 m (partly outside the target zone at half weight) → ₦2,454.94 on
16 Sep, all matching hand calculations. The driver breakdown API returned the
per-day miles and pay, and correction projections for both days showed zero
deltas. After the post-build review, a blocked-trip test was added (0 m, ₦0, no
entry; the next trip starts from 0 m), formatter-only edits to unrelated
lines were reverted, and every touched suite was rerun on the final code:
822 passed, and the only failures are the 12 environmental `test_w403a`
release-preparation tests. Those tests validate the compose and env templates
this batch edits, so that validation remains an open CI gate.
The full backend suite is left to GitHub CI (6 Linux shards) after an
owner-approved push. Nothing is committed or pushed.
Batch D record (26–27 Sep 2026, worktree `mobility-batch-d`, branch `batch-d`
from the committed Batch A head `7a9ceb0`; built in parallel with Batch B).
Scope: Paystack implementations of the payment and disbursement ports from
Paystack's public API documentation (read 26 Sep 2026; no account, dashboard or
provider call), tested only against synthetic recorded fixtures with an injected
HTTP transport. The client document's Paystack credentials are not recorded or
used. The controller stays `PAUSED — EXT-PAYMENT-PROVIDER` and the queue is not
flipped: `PKG-03 / W2-01C` resumes on the normal package path only when the owner
supplies Paystack test keys. Plan review (read-only Opus 5.5 stand-in): 6 material
and 6 minor findings; 10 adopted (test/live domain check, `sk_test_` refused in
production, recipient must match the frozen destination before any transfer,
resolver bound to the frozen payee/account versions, foreign charges acknowledged,
extra ordering and duplicate-reference tests), 2 rejected with reasons (the Batch D
handoff waives the live stack check and requires the specialist reviews). Owner
decision (27 Sep): the public route acknowledges `transfer.*` without reconciling
it, because the only transfer path reconciles in-request and §15.4 forbids that.

Delivered. `app/adapters/payments/paystack.py`: bearer client, HMAC-SHA512
`x-paystack-signature` verification, checkout initialize, verify, refund
create/list, exact kobo conversion, and `PaystackOutcomeUnknownError` for
timeouts, transport errors, 5xx, 429 and non-final statuses (never paid or
failed). `app/adapters/disbursement/paystack.py`: one line per submission, a
deterministic 50-character `cvp_` reference from the line idempotency key,
recipient checks, lookup (404 → not found, otherwise unknown), and webhook/poll
evidence with identical IDs and fingerprints; without an injected destination
resolver it reports no submission capability. `POST /api/v1/webhooks/paystack`:
503 without a key, 401 on a missing or bad signature, a Cardvert `charge.success`
recorded and enqueued through the existing ingestion, every other signed event
200 `accepted=false` with no writes. `PAYSTACK_SECRET_KEY` is blank in `.env.example`,
both release templates and both Compose files; `sk_live_` is refused in local/test
and `sk_test_` in production. Existing payment and payout routes, the worker and
every live-use gate are unchanged. No migration. OpenAPI, snapshot and
`schema.d.ts` moved together; the architecture inventory block was regenerated.

Evidence (27 Sep 2026). Backend (own database `mobility_test_d`, at most two
test containers across both sessions): `ruff check` and `ruff format --check`
pass on the changed files. The 11 files that exercise the change ran under
coverage: 751 passed; the 12 failures are the same environmental ones as Batch A,
all in `test_w403a_release_preparation.py` (no `docker` binary in the test image,
CRLF shell scripts); its environment-template parity tests, which cover
`PAYSTACK_SECRET_KEY`, pass. After the specialist-review hardening, the Paystack
adapter and API tests, the progress validator, the architecture inventory and
`test_openapi.py` ran again under coverage: 124 passed. Webhook ingestion is
proven through the API test client: a Cardvert charge creates one event and,
through the existing worker, one receipt; byte-identical and re-serialized
replays are duplicates; foreign charges, `transfer.*` and `refund.*` write
nothing; forged, other-secret, missing and blank signatures get 401; no key gets
503. Transfers are proven end to end through the existing provider-webhook and
poll routes with the Paystack adapter injected: submission through the worker,
`transfer.success` pays the line once, replay and poll add no event, and a late
success after `transfer.reversed` stays unapplied with the ledger unpaid. D32
changed lines against `7a9ceb0` from local LCOV: backend 381/387 lines (98.45 %)
and 116/122 branches (95.08 %). OpenAPI `--check` passes; `tsc` passes on the
regenerated `schema.d.ts`; the full Vitest suite passes 162 files / 1,044 tests,
including the R14-B fixtures. The full backend suite is left to GitHub CI
(6 Linux shards) after an owner-approved push. No live stack check: the Batch D
handoff waives it because the adapters are disabled without keys. Reviews: money
`PASS` and security `PASS` (both Opus 5.5 stand-ins, no required fixes); a
non-object `data` now gets 400/401 instead of 500, from the money review's notes.
Post-build minimal-change review (`vfd-change-reviewer`, Opus 5.5 stand-in):
`PASS` with four non-blocking notes and no fixes.

Remaining for key day (`W2-01C`, owner-supplied test keys): sandbox checks of
field names and timestamps, verify-transfer 404, reference uniqueness after a
failed transfer, metadata round-trip and key format; disable Transfers OTP and
confirm the fee bearer (amount vs `requested_amount`); wire an audited destination
resolver and the Paystack adapters into payout submit/poll and the worker; build a
checkout flow that stores Cardvert-issued references and checks the organization
and a same-origin `callback_url`; add a queued path (event row + worker) for
`transfer.*`, so a reversal after success is seen, before any transfer is
submitted; decide whether `sk_test_` should be refused for every deployed
environment name other than `staging` (today only the exact `production` value
refuses it); configure the webhook URL; Batch F edge work: a body-size cap and the
Paystack IP allowlist on `/api/v1/webhooks/*`. Nothing is committed or pushed.

B + D integration (28 Sep 2026, owner-approved commits). Batch B was committed
on `batch-b` (`e14149d`) and fast-forwarded onto `master`; Batch D was committed
on `batch-d` (`dbd41e1`) and merged. Template and compose conflicts kept both
settings; D's changelog row became v1.99; `openapi.json`, the snapshot,
`schema.d.ts` and the architecture inventory were regenerated from the merged
code (254 paths = 251 + B's 2 + D's 1). Merge-touched checks: `ruff` clean;
12 files (OpenAPI, inventory, audit-route coverage, authorization matrix, MVP
hardening, Paystack, v4, 0092, rule revisions, budget, release preparation):
611 passed, 12 environmental `test_w403a` failures, and one real defect the
authorization matrix found in Batch B: an unknown campaign on the v4 publish
route returned 503 while publishing was off instead of 404. The service now
checks the campaign before the switch; the matrix, v4 and rule-revision suites
then passed (59). `tsc` passes; full Vitest 1,061/1,064, and the three
`vendored-fonts` failures came from load while pytest ran alongside, since the
file passes alone (85/85). The full backend suite is left to GitHub CI after an
owner-approved push.

CI MinIO repair (28 Sep 2026, owner-approved). Every backend shard, e2e and R59
job on `4f318e3`, `batch-c` and `batch-e` failed before pytest: the pinned
`quay.io/minio/minio` and `minio/mc` digests are no longer publicly pullable
(also absent from Docker Hub). Unmodified `docker save` exports of those exact
images, from this laptop's cache, are attached to the repository release
`ci-images-minio-2025-07`; `scripts/ci_load_minio_images.sh` downloads them,
checks pinned SHA-256 sums before `docker load`, and replaces the three
pull-and-tag blocks in `ci.yml`. Evidence: the loader ran end to end in a Linux
container (both sums OK, both tags loaded) and
`tests/test_ci_integration_authority_r02.py` passes (73). The full suite on A, B
and D therefore had not run until this fix.

First full-suite CI run on A+B+D (`ba36073`, 28 Sep 2026) and repairs. Shards 0
and 5 passed; the failures were real and none environmental:
(1) Batch D: the Paystack adapters import `httpx`, which was only a dev
dependency, so the production API image could not start (e2e and R59 "API never
became ready"). `httpx==0.28.1` is now a runtime dependency in `pyproject.toml`
and `requirements-production.in`, and `requirements-production.txt` gains
`httpx`/`httpcore` with their PyPI SHA-256 hashes (other pins unchanged); the
production image was rebuilt with `--require-hashes` and booted with CI's e2e
environment (`/api/v1/health` 200).
(2) Batch B: `PAYOUT_RULE_MODEL_XOR_SQL` listed `max_payout_per_trip` in a
different position from migration 0092, failing the exact head-catalog test;
the model now matches the migration (same meaning).
(3) Batch B: `test_migration_0019` still expected `hourly_rate_naira` NOT NULL
on bindings at head; 0092 made it nullable under the terms-shape check.
(4) Pre-existing (unchanged since 8 Sep): `_settle_publication_write` set
`state='settled'` before reading the database clock, whose query autoflushed a
row violating `ck_report_publication_write_state` (ten report tests); the clock
is now read first.
Local evidence: the head-catalog, 0019 and report-issuance files pass (44).
`test_evidence_verification::test_satisfied_challenge_stays_satisfied_after_assignment_cancellation`
also failed in CI and at `edcda6b`: its earning was fixed at 26 Aug with a
30-day lookback but evaluated at real time, so it began failing on 25 Sep; it
now dates the earning from its own issue time (`319c2c4`).

A–E full-suite acceptance and D33 refresh (29 Sep 2026). Run `36491538535` on
`319c2c4` left five report-cleanup tests (the same autoflush ordering in
`sweep_report_publications`, clock now read before any change) and the
campaign-flow e2e ("Draft" also shown by Batch A's preparation summary; the
check is now scoped to the heading chip), fixed in `cf2dfd2`. Run
`36494571198` on `cf2dfd2` passed frontend checks, all six backend shards,
backend aggregate, R59 and desktop/mobile e2e; only the D33 gate failed with
"controlled baseline refresh required" for the new eligible sources. The
checker's refresh mode (Python 3.12.14, coverage 7.16.0, clean Linux clone of
`cf2dfd2`, base `319c2c4`) adopted that run's artifacts and a re-check passed.
Global line 86.78 → 88.32 %, branch 66.69 → 70.49 %; critical backend line
89.04 → 89.85 %, branch 69.10 → 71.12 %; critical frontend line 75.12 →
80.72 %, branch 64.06 → 69.82 %; no floor lowered. One exact-SHA CI run on the
refresh commit remains for acceptance.

D41 (29 Sep 2026, owner-approved). Run `36496910250` on the refresh commit
`2485184` again passed every test job but failed D33: identical code measured
18 backend lines below `cf2dfd2`, because concurrency tests take different
race paths (lines only in one run sat in conflict and retry branches of
`campaign_assignments`, `trips`, `disbursements`, `campaigns` and `billing`).
Rather than chasing each race path with tests, the owner adopted D41: ordinary
checks allow a 0.1-point dip below adopted floors (floors never lowered,
refreshes exact, D32 unchanged), and each batch branch must pass full CI before
it merges (`AGENTS.md`). `tests/test_changed_coverage_policy.py` passes (34,
including the new tolerance test). The checker is a policy file, so its change
needs a policy-only refresh that keeps the adopted floors.

Batch C record (27–28 Sep 2026, branch `batch-c` on `master` `4f318e3`).
Scope: automatic payout approval with safeguards, D39(c) as designed in D40 and
client answer item 8. Only clean `payout_v4` trip earnings may be approved by
Cardvert; everything else stays on the maker-checker path. Plan review (read-only
Opus 5.5 stand-in; the `verified-feature-delivery` reviewer agents were not
installed then): PASS WITH CHANGES, every finding adopted before build.

Delivered. Migration `0093` adds `payout_batches.approval_mode` and
`automatic_run_id`, the tables `payout_automatic_runs` (one per period),
`payout_automatic_controls` (one row: the pause switch and the system actor's
password fingerprint) and `payout_automatic_alerts`, and seeds a disabled system
actor ("Cardvert (automatic payouts)") that makes and approves automatic batches;
a check constraint allows only that actor to make automatic batches and never
manual ones, and downgrade refuses while automatic history exists. A worker cron
sweep (every sweep interval) makes at most one run per period (daily or weekly,
Nigeria time), enforced by the unique period key. A clean earning
is a `payout_v4` trip payout with no review flag of any status, no hold, no open
dispute for the driver, a current assessment, no debt, a verified payee, no
earlier automatic, active or failed line and no other non-voided entry on the
trip; flagged or adjusted trips are left out in the query so they never take a
scan place. Cross-campaign ceiling: per driver per Lagos day, earnings and
non-void, non-failed line cash (manual or automatic) must stay within one bound
day rate; differing rates or same-day hourly pay go to a person with a
`daily_limit` alert. The run limit stops at the first miss and never pays an
entry above the whole limit; one batch per driver per run; at most 200
candidates per run. Human approve/submit refuses automatic batches (409
`PAYOUT_BATCH_AUTOMATIC`); the submission claim re-checks cleanliness, the
switch, the pause and the actor's identity (email, name, role, disabled status,
password fingerprint) before any provider call, while lookups continue. While
automatic payouts are blocked, their unsent intents are left out of the due
queue so manual payments are never starved. Alerts cover failed and duplicate
payments, blocked submissions, limits and failed runs, with notices to active
admins. Finance API under `/api/v1/admin/payouts/automatic` (status, pause,
resume, release-unsent, alerts, resolve, reconciliation) and an `approval_mode`
filter on batch summaries. Audit subjects: runs resolve to the drivers in their
batches, alerts to their driver, the control row is actor-only. Admin
"Automatic payouts" page, "Automatic payout problems" under Finance in "Waiting
for you" (the approve/send count is now maker-checker only), and batch pages
show "Approved automatically by Cardvert" with no approve or send actions. The
worker keeps `DisabledDisbursementAdapter`, so a switched-on run records a
provider alert and creates nothing until W2-01C. `app/services/payouts.py` is
unchanged; no pay is recalculated.

Reviews and residuals. Security specialist (Opus 5.5 stand-in): PASS with four
low findings; name in the integrity check, the database pin on the actor and the
limit cap below ₦10^12 are fixed; an explicit actor guard in manual
approve/reserve was not added because the check constraint forbids the actor as
a manual maker and approval needs an active admin. Money specialist (Opus 5.5
stand-in): FIX; the high finding (blocked automatic intents starving the send
queue) and five low findings are fixed and now tested. The verification run found
two gaps, both fixed: the three new audit entity types had no subject
classification, and the worker cron count test expected 20 jobs. Money specialist
re-review of those fixes (Opus 5.5, clean context): PASS with two low test gaps
and two notes, none blocking. Post-build review (`vfd-change-reviewer`, Opus 5.5):
FIX with four findings, all adopted: a corrupted `₦` in a test comment restored;
§16.3, the v1.100 changelog row and D40 now name the name check, manual cash in
the ceiling and the due-queue exclusion; this record's schedule wording
corrected; and duplicate-payment alert scans now read newest first, so a new
duplicate is never hidden behind 200 already-alerted ones (tested). Residuals for
the owner: a `users.py` guard refusing edits to the system actor (today an edit
only blocks automatic runs); the ceiling counts a line's full amount on every
day its trip touched (conservative for cross-midnight trips); no test yet proves
that another day's submitted line is left out of "awaiting provider" or that
manual failure audits cannot crowd the blocked-submission scan; while the actor
is invalid, no `submission_blocked` alert is raised (only the run's
`run_failed` alert, and none if the switch is also off); entries excluded for
drift, `not_daily_rate` or an unverified payee still take candidate places until
handled by hand.

Evidence (28 Sep 2026). Backend (own database `mobility_test_c`; at most one of
this session's containers at a time beside Batch E's two, as the owner allowed):
`ruff check` passes and `ruff format --check` passes on the files Batch C adds;
pre-existing unformatted lines in touched files are left alone. The 39 files that
exercise the change ran under coverage: 1,068 passed and 15 failed. Twelve are
the environmental `test_w403a_release_preparation` failures seen in Batches A, B
and D (no `docker` binary in the test image, CRLF shell scripts); one is
`test_w403b_synthetic_path` (no `npm` in the test image); two were the audit
subject and cron-count gaps above. After the fixes, the automatic-payout, audit
subject, worker substrate and W403B files reran: 110 passed, only the `npm`
failure remaining. After the post-build review fixes, the automatic-payout,
progress-validator and architecture-state files reran under coverage: 89 passed. `tests/test_automatic_payouts.py` now has 38 tests, including
the queue-starvation, manual-cash guard, actor-name, audit-subject and
duplicate-alert cases, and
the migration test covers the actor pin both ways. OpenAPI `--check` and the
architecture inventory check pass, so no baseline moved. D32 changed lines
against `4f318e3` from local LCOV: backend 679/746 lines (91.0 %) and 163/200
branches (81.5 %); frontend 102/102 lines (100 %) and 148/166 branches (89.2 %).
Frontend: `tsc` and ESLint pass; Prettier passes with `--end-of-line auto` (the
Windows checkout gives Batch C's files CRLF; Git stores LF). The full Vitest
suite under coverage passed 163 of 169 files; the six failures were 5-second
timeouts in files Batch C does not touch, and all six, plus a load timeout in the
batch-forms test, pass when run on their own. The full backend suite is left to
GitHub CI (6 Linux shards) after an owner-approved push.

Live check (synthetic values only: daily, run limit ₦20,000, ₦8,000 day rate) on
a fresh `mobility_live_c` database migrated by alembic to `0093`, so the actor
and control rows came from the migration. Driver A (one campaign, ₦3,357.89) was
approved by Cardvert, sent by the disbursement sweep through the fake adapter
and paid by a signed fake webhook (line succeeded, entry paid, batch completed,
maker the system actor, no human approver). Driver B earned ₦16,000.00 on
20 Jul across two campaigns (₦3,357.89 + ₦4,642.11 + ₦8,000.00): all three
trips stayed manual as `daily_limit` exclusions with one alert (earned ₦16,000,
ceiling ₦8,000). A second sweep in the period returned `already_ran`; no review
flags were raised. Over HTTP (uvicorn): status 200 (switched on, identity ready,
provider not ready because the API keeps the disabled adapter); a one-letter
pause reason 422; pause 200 and a second pause 409; release-unsent 200 with
nothing to release; resume 200; resolving the alert 200 and again 409; alerts
then empty; reconciliation for 28 Sep showed one run, one succeeded line and
none awaiting the provider; batch summaries named "Cardvert (automatic
payouts)" with no checker; a driver got 403 and no token 401. The admin screens
were not opened live, to stay within the container limit; they are covered by
Vitest.

Left unset in `.env.example`, both release templates and both Compose files:
`PAYOUT_AUTOMATIC_APPROVAL_ENABLED=false`, `PAYOUT_AUTOMATIC_FREQUENCY` blank
(client Q4), `PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN` blank, and
`PAYSTACK_SECRET_KEY` blank. The controller stays
`PAUSED — EXT-PAYMENT-PROVIDER`; nothing is promoted.

Batch C integration (28 Sep 2026, owner-approved). The security review had run
on an earlier branch state, so a fresh security specialist (clean-context,
reported `claude-opus-5-5`) reviewed the final `batch-c` diff: PASS WITH
FINDINGS, no merge blocker. M1 (medium): one admin can add and verify a bank
account (D29) and, with no batch approver, automatic payouts would pay it
unseen. Fixed: an automatic payment needs a bank account version with an
earlier `succeeded` line, else `new_bank_destination` keeps it manual (D40(b)
and §16.3 updated). L1: `update_user` now refuses the system actor
(409 `SYSTEM_ACCOUNT_READ_ONLY`), the owner-approved guard. Recorded, not
adopted: L2 the open-dispute check takes no lock (narrow window; the manual
path has no dispute gate), L3 alert creation writes no audit event (rows are
durable; resolution is audited), L4 the run-level audit event maps every
driver in the run as a subject though it carries only run totals, L5 the
200-entry scan cap can delay newer clean earnings behind long-excluded ones
(availability only). The branch was squash-merged as one owner-authored commit
because its commits were authored as `Claude <noreply@anthropic.com>` and two
were work-in-progress.

Batch E record (28 Sep 2026, worktree `mobility-batch-e`, branch `batch-e` from
`4f318e3`, built in parallel with Batch C). Scope: D39(d) in-app complaints with
a Customer Service inbox, under the contract in
`.codex/delivery/cardvert-batch-e/contract.md`. Plan review (Opus 5.5
`vfd-plan-reviewer`): PASS WITH CHANGES, 5 material and 9 minor findings, all
adopted (§10 there): every complaint route scopes the complaint before any other
check; follow-up, reply and PATCH lock the row; messages record the status they
left, so a retry with `resolve` flipped is 409; advertiser viewers may raise and
follow up; fixed dedupe keys; `reference-options` declared before
`{complaint_id}`; the sender reads only `you`, `your_team` or `terrax_media`;
driver campaign and payout references limited to the driver's own jobs and pay
entries; a technical limit of 100 messages per complaint; §20.4 records how
complaint text is kept and the driver manual-contact exception.

Delivered. Migration `0094` (`down_revision` `0092`; re-pointed to Batch C's
`0093` at integration) adds `complaints` and the append-only
`complaint_messages`; downgrade refuses while any complaint exists. Five driver
routes, five advertiser routes and four admin routes under
`/api/v1/driver/complaints`, `/api/v1/advertiser/complaints` and
`/api/v1/admin/complaints`. The owner rules: a driver complaint belongs to the driver
profile, and an advertiser complaint to the organization, which every active
member can see. Any active admin handles complaints (no new role); the assignee
must be an active admin. Foreign and unknown references return the same 404
`COMPLAINT_REFERENCE_NOT_FOUND`, and foreign and unknown complaints the same 404
`COMPLAINT_NOT_FOUND`, with nothing written. Each mutation writes one audit
event with no message text; exact retries converge and changed reuse is 409.
Four notification types: staff get in-app notices (the assignee, or every
active admin); advertisers get in-app plus the existing preference-governed
email (static templates, identifiers only); drivers get in-app only and no
manual contact task (a stated §20.2 exception). The audit-subject registry
covers `complaint`, and the DSR inventory gains `customer_service_complaints`.
Screens: driver `/driver/help` (Help link in the driver header), advertiser
`/advertiser/help` (nav "Help"), staff `/admin/complaints` (nav "Customer
Service") and "Complaints to answer" in the Customer Service section of
"Waiting for you". They cover loading, empty, error-with-retry, pending and
plain-error states, show times as "(Nigeria time, WAT)", and put no IDs or
hashes on driver or advertiser screens. The categories are a neutral, labelled
default. OpenAPI, the snapshot and `schema.d.ts` moved together; architecture
§20.4 [BUILT], a §30 row and changelog v1.101 (v1.100 is Batch C's). No decision
row changes.

Reviews. Security and privacy specialist (read-only clean-context subagent,
reported model Opus 5.5 `claude-opus-5-5`): PASS WITH FINDINGS. It confirmed
tenant isolation, non-enumeration, revocation, admin-only staff routes, the
assignee check, idempotency and races, server-action validation and screens
without IDs. It found one low defect: a NUL character in a message made
PostgreSQL fail with a 500 whose exception text (sent to Sentry) could include
the message. Fixed: the schemas refuse NUL with 422. Also adopted: the
category check now also requires lowercase with no spaces, as the contract
says (portable to the SQLite test metadata); a revoked or missing account now
gets "Your account can't use Help right now" instead of "record not found";
and tests for revocation on every advertiser route and for an inactive
organization, for identical foreign and unknown complaint 404s on driver and
advertiser detail and follow-up, and for advertiser email rows without message
text. Not adopted, as optional: a stricter UUID pattern for the reference value
(the backend validates it), a UUID pre-check on page URLs (a malformed link
shows "couldn't load"), and a database trigger for append-only messages (ORM
guards, as the contract specifies). Post-build minimal-change review
(`vfd-change-reviewer`, Opus 5.5 `claude-opus-5-5`): FIX with four
documentation findings (a placeholder, a CI claim about an unpushed branch, an
inaccurate description of coverage misses, and a stale handoff file, now
removed), all fixed; then `PASS`.

Evidence (28 Sep 2026). Backend on the shared `cardvertmain` PostgreSQL 16 +
PostGIS 3.4 container with its own `mobility_test_e` database and Redis 7
(databases 12–14), run from a `cardvert-dev:py312` container. The 13 files that
exercise the change ran under coverage: 138 passed. They are: complaints API
and service, migration `0094`, the authorization denial matrix, audit-route
coverage, audit subjects, the DSR inventory registry, architecture current
state, MVP hardening, OpenAPI, the notification feed, review notifications and
email delivery architecture. A first run after the specialist fixes caught a
real regression: a regular-expression category check broke the SQLite test
metadata (58 errors). It was replaced by a portable check, and the rerun
passed. `ruff check .` passes; `ruff format` is clean on the changed files.
The inventory is regenerated, OpenAPI `--check` passes (the new checks don't
change the schema) and the progress validator passes. D32 changed lines
against `4f318e3` from local LCOV: backend 571/579 lines (98.6 %) and 99/102
branches (97.1 %); frontend 193/210 lines (91.9 %) and 183/197 branches
(92.9 %). Backend misses: the replay branch of the concurrent-raise race
(`services/complaints.py:429`, not exercised by a test) and route and service
lines after an `await` that this coverage configuration does not trace.
Frontend misses: the route-file wrappers and `loading.tsx` files. These numbers
come from the batch's ad-hoc LCOV script
(`.codex/delivery/cardvert-batch-e/d32.py`), because the repository's
`scripts/check_changed_coverage.py` needs CI provenance; CI's run of that
checker is the gate that counts. Frontend
(Node 26.3.0 container): the full Vitest suite passes 170 files / 1,106 tests,
including the R14-B fixtures, with `--testTimeout=30000`. With the default 5 s
timeout, three `vendored-fonts` tests timed out scanning the Windows bind
mount; that file passes alone (85/85). `tsc`, ESLint and Prettier are clean on
the changed files. Live check (earlier in this batch, uvicorn + `next dev` on a
scratch demo database, real HTTP and Playwright):
- raising a complaint works, and foreign and unknown references both return
  the identical 404;
- an exact retry converges;
- staff reply and resolve work;
- the driver sees "Terrax Media", and the driver's follow-up reopens the
  complaint;
- an advertiser viewer can raise a complaint, and the owner sees it as
  "your_team";
- email rows exist only for advertiser members, with identifier-only payloads;
- each of the six mutations wrote exactly one audit event without message text;
- driver screens show no hashes or IDs and read "(Nigeria time, WAT)".
The specialist-review fixes (NUL refused, the category check, the account
message) are proven by tests, not re-run live. The full backend suite is left to
GitHub CI (6 Linux shards) after the owner-approved push of `batch-e`. Nothing
is merged to `master` or deployed.

Residuals and open client questions: (1) the complaint category list (a
neutral labelled default is in use); (2) any response-time target (none is shown
or enforced); (3) whether drivers should get email or WhatsApp for replies
(in-app only today, per §20/D18, with no manual contact task); (4) whether
advertiser complaints are visible to the whole company (today) or only to the
person who raised them; (5) how data-erasure requests treat complaint text
(kept as the customer-service record and counted in the DSR inventory; any
erasure is a manual staff decision). At Batch C integration, `0094` is
re-pointed to `0093` and the migration-head tests and inventory are rerun.

Batch E integration (28 Sep 2026, owner-approved). Squash-merged onto `master`
after Batch C as one owner-authored commit. `0094` now revises `0093`
(`test_migration_0094` updated); notification types, the "Waiting for you"
test, migration-head tests, OpenAPI, snapshot, types and the architecture
inventory were merged or regenerated (changelog v1.101 above C's v1.100).
Two cross-batch defects found by running the shared tests: (1) C's
`payout_automatic_alerts` and `payout_automatic_controls` were not classified
in the DSR inventory; alerts are now counted per driver
(`automatic_payout_alerts`) and the pause switch is an operator-authority
exclusion. (2) `ck_complaints_category` used `NOT LIKE '% %'`, which metadata
DDL renders as `'%% %%'`, so model-built test databases enforced a different
rule from migrated ones; both now use `category = replace(category, ' ', '')`.

**Client visual-direction reduction (24 Sep 2026):** The owner reports the
client rejected former directions 1, 2, 4, 5, 6, 7 and 8 and directs their
implementation traces and dedicated assets removed. Retain former directions
3 (`ivory-ledger`), 9 (`broadside`), 10 (`dispatch`) and 11 (`ledger`) as new
Directions 1–4, in that order. The frontend theme registry, default and
persisted-theme bootstrap, scoped CSS, unused theme-only fonts/assets, picker
tests and current design documentation are owned by this bounded request.
Former Direction 3 becomes the default; stale stored selections fall back to
it. Preserve the unrelated uncommitted work, public Terrax marketing styling,
historical decision records, API contracts and the paused package queue.
Verify registry/CSS parity, selection, stale persistence and a frontend build.
Verification: 118 focused theme/font tests passed, TypeScript passed, the
production frontend build passed, and a fresh production preview on port 3002
showed exactly four picker choices, Ivory Ledger default colour `#efe9d8`,
Direction 4 selection/persistence, and fallback to Ivory Ledger from an obsolete
stored choice. The existing port-3000 service served an older build during
verification and requires restart to display this checkout. The controller
remains `PAUSED — EXT-PAYMENT-PROVIDER`.

**Human-journey UX audit and bounded copy/flow fixes (24 Sep 2026):** The owner
directs a first-time-user review of the advertiser, driver, Terrax Media admin
and public journeys, a comparison of the client guide *How Cardvert Works*
(generated 17 Sep 2026) with observed behaviour, and bounded fixes for
confusing copy, navigation, error handling and discoverability. Evidence comes
from a separate main-checkout stack (`cardvertmain`, ports 3001/8001, migrated
to `0090`, demo seed, default pre-approval privacy configuration) plus the
existing `21a5981` livecheck stack for synthetic-mode comparison. This is a
bounded direct-owner batch outside the executable queue: the controller stays
`PAUSED — EXT-PAYMENT-PROVIDER`, no package is promoted or reordered, and no
external or live-use gate changes. Single writer: this Claude Opus 5.5 session;
reviewers are read-only. Admitted batch (IDs `UX-01…`): UX-01 notification
read actions send no body media type and older notifications are reachable
(issues.md QA-17/QA-18); UX-02 advertiser planning-source page renamed and
rewritten in plain language, with a gated state instead of a crash when privacy
approval is absent, and support hashes collapsed behind a labelled disclosure
(G-37 remains an owner decision; nothing is deleted); UX-03 admin planning page
gated state instead of a crash; UX-04 report and map show "no report yet" when
no run exists and a privacy-approval state when gated (QA-02); UX-05 campaign
page shows only actions the server accepts for the campaign's status, human
status and artwork labels, and a terminal-aware preparation summary; UX-06
campaign form wording ("Daily budget", wizard/recovery guidance, QA-09/QA-11);
UX-07 viewer role sees read-only company and campaign surfaces and a permission
message instead of an uncertain-result retry (QA-03); UX-08 driver journey and
tracking copy without engineering vocabulary, and Track distinguishes a paused
eligibility from "no campaign" (QA-13); UX-09 admin navigation grouped and
scrollable at laptop heights (QA-04); UX-10 an invited driver applicant cannot be
activated through the generic user-status control, server and UI (QA-15,
security review required); UX-11 an offer without complete frozen terms cannot
be accepted from the UI and says why (QA-16). Not admitted and recorded in the
audit: notification record links (API contract change), physical-check pickers
(QA-05), driver evidence renewal (NX-05), payment instructions (G-19), demo seed
coherence (QA-10), campaign completeness rule (QA-01), naming/time-zone wording
(G-30), capability page exposure (G-35). Gates: one independent plan review
before product edits; security review for UX-10; one consolidated post-build
review. No provider call, deployment, production-data mutation, invented
policy/legal/payment/support value, relaxed authority check, new skip,
coverage-floor change, commit or push is authorized. The uncommitted CV-01–CV-17
and test-audit work is preserved; overlapping files are edited in place.

Independent plan review (read-only reviewer) returned `FIX`; all seven blocking
amendments are adopted before any product edit. (1) UX-10 evaluates the
post-update role: `invited → active` is refused when either the current or the
requested role is driver, and an invited driver's role cannot change, closing a
role-flip bypass; `create_user` creating an already-active driver is recorded as
residual risk for the security review. (2) UX-01 updates the existing
notification and BFF route tests, and malformed `limit`/`offset` return 400.
(3) UX-02/UX-03 load every read (lists, per-link recommendations, per-campaign
zones, admin insights) through the existing `loadAdvertiserPageData` /
`DataUnavailable` contract, render no write form when gated, keep explicit
option `value`s, and keep hashes inside the ready-state branch under the
existing "Technical reference" label. (4) Signed-in copy keeps "Cardvert"
(G-30 stays an owner decision), and UX-11 promises no operations process.
(5) UX-05 keeps A-13's campaign-review state and non-authorization statement in
plainer words. (6) UX-06 rewrites the two QA-11 wizard tests and keeps the
currency label dynamic. (7) E2E selectors and unit tests named by the reviewer
change in the same batch; the UX-09 admin nav relabels are cut (grouping and
reachability only).

Post-build record (24 Sep 2026, uncommitted working tree). Security review of
UX-10 returned `FIX`: an admin could flip an invited applicant to advertiser
(recoverable while invited), let them reset a password, and flip back to
driver. Adopted: `update_user` refuses both activation and any role change while
the user has a driver application and no completed setup token
(`DRIVER_ACTIVATION_REQUIRES_SETUP`); residuals recorded are that non-admin role
changes never revoke sessions, and that an applicant activated through the old
bypass cannot be reactivated after suspension. The consolidated post-build
review returned `FIX` with three blocking items, all adopted: live evidence for
UX-03/UX-06/UX-09, QA-03 wording (campaign-detail and edit write controls stay
visible to viewers — residual, server still refuses), and changed-line coverage
with added tests. Most non-blocking points were adopted, including restoring
the lawful-basis status line on the retargeting form in plainer words, neutral
fallback report copy, and `aria-describedby` on the disabled Attach/Connect
buttons. Evidence: `tsc`, ESLint and Prettier (explicit file list) pass; full
Vitest with coverage 156 files / 1,024 tests pass (the font inventory tests
need a longer timeout on the Windows bind mount; they pass with 60 s). Changed
lines of the 30 touched frontend files against `21a5981` (also counting CV
hunks in shared files): 94.6% lines, 82.8% branches, computed directly from
LCOV, not by the official D32 checker, which needs a full backend LCOV. Backend:
`ruff` passes; `test_admin_users.py` 33/33 and with `test_driver_account_setup.py`
40/40; `users.py` new lines fully covered including branches; red checks fail
the four activation-bypass cases and the role-change case with the guard
removed. Live on the main stack: notification paging (20 of 35 → 35) and both
read actions (200, previously 415), retargeting and admin planning gated states,
report/map privacy and no-run states, finished-campaign summary, viewer
read-only screens, wizard copy and empty-attach guard, driver journey and Track
copy, offer without terms, and the admin sidebar at 1366×695 (sign-out
reachable). Not run: `analytics`, `campaign-flow` and `w401c` E2E specs (updated
selectors only). No OpenAPI/§9 baseline, migration, provider, seed or coverage
baseline changed. Findings, guide corrections and the open/owner/client lists
are in `issues/product-ui-review/human-journey-audit-2026-09-24.md`; the
`issues.md` recheck marks QA-02/03(partial)/04/09/11/13/15/16/17/18 fixed and
adds QA-19–QA-23. Nothing committed or pushed.

**Low-signal unit-test audit (24 Sep 2026):** The owner directs a repository-wide
comparison of backend and frontend unit tests with the existing E2E journeys,
and deletion of tests that cannot detect a realistic regression beyond those
journeys. Preserve tests for distinct failure modes, contract boundaries,
security/privacy/money invariants, concurrency, offline recovery, and CI
authority. This is a bounded test-only maintenance request outside the package
queue; it does not promote PKG-03, alter product behavior, lower D32/D33/D36
coverage authority, or overwrite the uncommitted 23 Sep CV-01–CV-17 work.
Use focused verification of changed suites and the existing test-inventory
gate; record actual deletions and remaining limits here after the audit.
The audit inventoried 246 backend test files, 153 frontend unit-test files and
22 browser specs. The clear E2E overlap was the public landing CTA, anchor,
namespace and legacy-redirect assertions, mobile-menu destination assertions,
and the basic credential-form presence check: the existing real-browser
landing and login journeys cover those outcomes. Five frontend cases were
removed net, while a distinct keyboard skip-link/main-landmark assertion was
retained. Six backend cases were removed: a snapshot path-set comparison that
`test_openapi_matches_committed_json_artifacts` supersedes; mocked demo seed
success, password-length and migration-head checks exercised by the real-stack
E2E seed command; a README keyword check that could pass with incorrect
instructions; and the repository-progress self-check duplicated by CI's
standalone `validate_progress.py` invocation. The BFF route-inventory test was
kept and made Windows-path-safe after the first complete frontend run exposed
its separator-dependent failure. No product, E2E, coverage-policy or baseline
file changed. Final frontend verification: 152 files / 1,016 tests passed;
TypeScript and the progress validator passed. Frontend line coverage is
4,377/5,789 (75.6089%) against the committed 75.1183% floor; branch coverage
is 4,214/6,521 (64.622%) against 64.061%. Local backend pytest execution was
unavailable because this checkout has no installed pytest/application test
environment; the affected backend tests were checked against their stronger
gates and syntax-compiled. The existing CV-01–CV-17 candidate remains
uncommitted.

**Post-theft current-state reconciliation and bounded fixes (23 Sep 2026):**
The owner's laptop was stolen; local `master` is a fresh clone of
`origin/master` at `21a5981` (last push 16 Sep 2026, exact-SHA CI green per
owner). Owner directs: establish the current Cardvert issue state from every
local source plus the four 21 Sep review leads, distinguish missing code from
never-implemented recommendations, then fix confirmed issues the delivery rules
permit. The complete coverage matrix is
`issues/planning/current-state-reconciliation-2026-09-23.md`; it finds no
evidence of code newer than `21a5981` in the clone or on GitHub (laptop-only
work can be neither confirmed nor ruled out). This is a bounded direct-owner
batch outside the executable queue: the controller remains
`PAUSED — EXT-PAYMENT-PROVIDER`, no package is promoted or reordered, and every
external/live-use gate is unchanged. Single writer: this Claude Opus 5.5
session; read-only independent reviewers only. Admitted batch:
CV-01 lookup-only disbursement reconciliation must not require historical
batch actors to remain active admins (SUBMIT keeps that authority);
CV-02 D29/AUT-007 one active advertiser membership per login (index violation
mapped to a 409 in the company service, additive migration `0090` partial unique index that refuses, rather than
repairs, existing conflicts, and fail-closed resolution);
CV-03 admin physical spot checks no longer hidden behind the mixed 100-row
verification cap (additive `verification_type` filter);
CV-04 per-trip ledger index in `ReportCohort.final_cost` (identical results);
CV-05 contact-task driver names in one query;
CV-06 creative replacement upload race;
CV-07 advertiser edit of draft/rejected campaigns through the existing PATCH;
CV-08 creative rejection reasons visible to the owning advertiser;
CV-09 driver home/profile counts from server totals;
CV-10 tests use only `TEST_DATABASE_URL`, never the app `DATABASE_URL`;
CV-11 complete readable quotation scope/payment terms in place of raw JSON;
CV-12 advertiser notifications for campaign rejection, creative decisions and
new quotation revisions through the existing typed outbox and D24 preference;
CV-13 scrollable theme picker; CV-14 Dispatch sidebar hover contrast (only if
measured below WCAG AA); CV-15 notification badge/list kept during background
refetch; CV-16 truthful advertiser map heading; CV-17 campaign window inputs at creation
and edit interpreted as Lagos time, matching the existing change panel (found
during CV-07 preparation). Explicitly not admitted and
recorded open in the matrix: D30/ONB-003 duplicate identity (dedicated
privacy/migration packet; public non-enumeration conflict), driver
renewal/phone-verification/WhatsApp-consent journeys (privacy packet and
`EXT-MESSAGE-COPY`/`EXT-LEGAL-PRIVACY`), NX-13 advertiser-organization
recovery, Argon2 offload, ping-queue and shard changes (measurement first),
and every owner/external decision. Gates: one independent plan review before
edits; money specialist review (CV-01); security/database/privacy specialist
review (CV-02, CV-08, CV-10, CV-12); one consolidated post-build review.
CV-03/CV-12 move all three §9 baselines together and rerun the frontend
tracker/queue fixtures. No provider call, deployment, production-data
mutation, invented policy/copy/legal value, relaxed authority check, new skip
or coverage-floor change is authorized. No commit or push without separate
owner approval.

Independent plan review (read-only Opus 5.5 reviewer) returned `FIX` with three
blocking amendments, all adopted before any product edit. (1) CV-02 sweeps
fixtures that hold two active memberships for one login: the Package 5
newest-membership test becomes a D29 invariant test, the retargeting fixture
flushes its disable before the replacement activation, and the 25 Aug Package 5
receipt that "governed advertiser output deterministically selects the newest
active organization membership" is superseded by D29. (2) The three membership
consumers (`organizations.py`, `audience.py`, `disclosure.py`) stop selecting
the newest row and fail closed on more than one, matching architecture §23's
D29 target. (3) CV-17 owns `lib/campaigns/schema.ts`, `campaigns/new/actions.ts`
and `wizard.tsx`: one shared Lagos converter, datetime-local shape validation,
"(Lagos time)" labels, and the edit form sends only changed fields; runtime-zone
display formatting is recorded as a separate residue. Non-blocking amendments
also adopted: CV-01 re-raises the deferred authority error immediately after
the action is chosen, records exempted inactive actors in the authorization
audit, adds a `QUERY_ONLY` case and a §16.3 note; CV-02 removes the unreachable
duplicate-membership branch and documents the operator runbook for moving an
advertiser between companies (linked to NX-13); CV-03 states the newest-100
bound; CV-10 points README at a dedicated test database; CV-12 updates §20.2;
CV-07 adds a PostgreSQL PATCH-then-resubmit API test; D32 changed-code and
baseline coverage is checked against base `21a5981`.

Post-build record (23 Sep 2026, uncommitted working tree on `21a5981`).
Specialist reviews: money (CV-01) `PASS`, adopting the §16.3 error-precedence
note and a recovery-incident lookup test; security/database/privacy (CV-02,
CV-08, CV-10, CV-12) `PASS`, adopting constraint-name assertions and the
runbook `NOWAIT` retry line. The consolidated post-build review returned `FIX`.
All of its items were adopted: this record and the D32 figures; a matrix
follow-up row for the existing advertiser review-history schema breadth; the
edit form keeping the advertiser's input after a failed save; and direct
service tests for the CV-02 conflict and CV-12 creative notices. CV-11 is
described as complete readable terms, not lossless. The CV-12 exact-retry
dedupe claim is withdrawn as untested. The `.codex` plan-ledger decision states
are superseded by the matrix.

Red/green evidence came from temporarily removing the product change with the
new test kept. It covers CV-01 (5 R21 cases plus the recovery incident),
CV-02 (3), CV-03/05/10/12 (6), CV-04 (by mutation), the frontend (23) and the
edit-form input retention (1).

Local verification used Docker with PostGIS 16 and Redis, without MinIO,
ClamAV, Caddy or Docker-in-Docker. Fixed-baseline results:
- Full backend suite in four shards: 2,851 passed, 60 failed plus 6 errors,
  12 skipped. Each failure was attributed to the environment: missing
  docker/npm binaries, CRLF shell scripts, and memory or import timeouts under
  parallel load. The load failures pass on rerun, and three failures reproduce
  identically on a clean `21a5981` export.
- Adjacent money suites: 61/61.
- Final reruns of the R21, R22 and notification suites (44), and the
  organization, notification and disclosure suites (50).
- `ruff check` passes. CI runs only `ruff check`; the changed Python files that
  `ruff format` would still reformat were already unformatted at `21a5981`.
- OpenAPI `--check` and `validate_progress` pass.
- Frontend: Prettier on the changed files, ESLint and tsc pass; the full Vitest
  run passes 153 files and 1,021 tests, which includes the R14-B fixtures; and
  `next build` passes.
- A fresh database migrates 0001→0090 and seeds. A desktop and mobile
  Playwright journey creates a campaign, edits it, saves and edits it again;
  09:00/18:00 Lagos time is stored as 08:00Z/17:00Z.

D32 changed-line coverage against `21a5981` is 96.05% of lines (243/253) and
81.17% of branches (181/223). This is local LCOV: the full-suite run merged
with the direct service tests. The new eligible files change the D33
inventory, so after an owner-approved push the first exact-SHA CI run must be
followed by a controlled `coverage/baseline.json` refresh from that run's
artifacts. Until that run is green, this batch is a local candidate only.

Measurements that decided the non-admitted leads are below.
- Dispatch sign-out hover contrast was 2.05:1 and is now 5.32:1; the other
  sidebar pairs measure 6.5–13.4:1.
- Argon2 verify takes about 21 ms median (25 ms p95), and moving it off the
  event loop gave no measurable benefit. It stays open for load evidence.

Incident disclosure: a container-side `prettier --write` misread CRLF
checkouts and rewrote about 440 unrelated files. All of them were restored with
`git checkout --` before any further edit, and formatting afterwards used an
explicit file list. `frontend/src/app/globals.css` was already not
Prettier-clean at `21a5981` and carries only the CV-14 two-line change.

An untracked root `issues.md` was created by a separate session; this batch
does not own it. Nothing is committed or pushed; that awaits owner approval.

**Product-completion P6 local closure candidate (16 Sep 2026):** The approved
P6 sequence is integrated locally through `1da0aee`: the PRD and P4 money
verification are accepted; the non-money visual/state, dependency/isolation,
MapLibre compatibility, changed-coverage and final account-setup corrections
are committed; exact changed coverage passes at 94.1667% lines and 80.6202%
branches; the final clean-context correction review returned `PASS`. Recorded
local evidence includes 1,003 frontend tests, 2,871 backend tests, focused
desktop/mobile real-stack browser flows, the 14-case fail-closed database
fixture matrix, production build, type/lint/format checks and D33 provenance
verification. This remains a local completion candidate until the final
integrated commit is pushed and every required exact-SHA GitHub CI job passes;
external live-use gates remain unchanged.

**CI throughput correction (15 Sep 2026):** Owner directs the existing acceptance
pipeline to retain all six authoritative backend shards, R59, changed-code
coverage, and ordinary desktop/mobile E2E while removing provably unused repeated
browser provisioning from backend shards and removing coverage as an execution
prerequisite of E2E. Node/Chromium remains provisioned only on deterministic
backend shards that own the storage-CSP or W4-03B synthetic browser tests, while Caddy remains
provisioned on the shards owning either live Caddy test;
PostGIS, Redis, MinIO, ClamAV, exact-SHA binding, complete shard manifests and
coverage aggregation remain unchanged on every applicable shard. E2E may start
after `quality` while coverage independently remains fail-closed on `backend` and
`quality`; all named checks remain required for acceptance. Evidence: workflow
contract regressions plus YAML parse and focused CI-authority/coverage/R59 tests.
Exact-SHA run `35064838661` exposed the omitted W4-03B browser owner after 480
tests in shard 5 passed; commit following `38357f3` adds that owner to the same
conditional provisioning contract before rerunning the full exact-SHA pipeline.

**Cardvert product-completion programme (14 Sep 2026):** Owner directs “P0 is
green, on to the rest, ASAP” and authorizes the GPT-6 product-completion
blueprint reviewed at `e952341` on the accepted P0 lineage now at `533f62d`.
This is a bounded direct-owner programme outside the executable package queue;
the `PKG-03 / W2-01C` external-provider pause and every live-use gate remain
unchanged. Source inventory is C02–C16 plus V01–V07 and E01–E07 from the
blueprint: P1 owns advertiser quotation, change preview/confirmation, safe
feedback, artwork recovery, preparation and report clarity; P2 owns driver
application/access recovery, renewal, page resilience, phone setup, tracking
recovery and earnings clarity. After both are independently verified and
admitted, P3 owns non-money operator discovery/evidence/assignment/
measurement/contact/closeout and P4 owns payout selection, debt, independent
approval, provider-neutral submission and reconciliation. P5 then creates
`docs/product-requirements.md`; P6 closes integrated browser/state,
environment-isolation, dependency-security and exact-SHA CI acceptance.
Maximum implementation concurrency is two. Phase I uses two Sol High owners
because P1 crosses commercial/money and public-error boundaries while P2
crosses security/privacy, tracking recovery and earnings presentation. P1
holds the exclusive Phase-I lease on generated OpenAPI/schema fixtures, shared
UI/error utilities and cross-cutting auth; P2 must report a needed shared
contract and wait for serialized integration rather than editing those files.
Controller alone edits this ledger. Independent aggregate plan review precedes
product writes; money/security/privacy/tracking specialist review and one
consolidated post-build review gate admission. No live provider call,
deployment, production-data mutation, invented policy/legal/commercial value,
background-tracking expansion, relaxed authority check, new skip or coverage
floor change is authorized. P0 is accepted by exact-SHA GitHub run
`34853561120`: all 12 jobs passed, including 753 frontend tests, 2,813 backend
tests, R59, changed coverage, and 96 ordinary desktop/mobile E2E passes with
the 18 existing justified skips.

Phase-I independent Sol High plan review returned `FIX`; the controller adopts
its four blocking amendments before dispatch. P2 additionally owns
`frontend/src/components/driver/**`, `frontend/src/lib/driver/**`,
`frontend/src/lib/trips/**` and driver-only PWA/E2E files, but neither owner may
edit shared Playwright fixtures, seed helpers, `tests/conftest.py`, notification
infrastructure, formatting utilities or contract baselines concurrently. Any
driver auth/generated-contract need becomes a concrete P2 handoff: P2 pauses
that mutation, P1 serially integrates it after synchronisation, and P2 then
verifies the resulting driver flow. C03 is one read-only server preview (zero
campaign/request/revision/allocation/audit writes) plus a separately confirmed
command bound to previewed inputs/source digest, revalidated under existing
locks; stale confirmation is denied and duplicate confirmation converges on one
authoritative result. C05 localises only optional history/labels: current-trip,
activation, ownership, earnings-summary, hold and debt authority continue to
fail closed, and reconnect reveals actions/money only after a successful fresh
read. C06 preserves four distinct authorities—public status reference,
expiring onboarding-evidence access, administrator-authorised account setup,
and post-activation password reset—plus terminal revocation, replay denial,
duplicate conflicts, reviewed renewal, rate limits, recipient privacy and
public non-enumeration. Per-item acceptance records focused red/green evidence,
server-value parity, database/audit non-mutation where relevant, stale and
double-submit outcomes, real-backend desktop/mobile proof, and named specialist
review. Owners use separate browser ports and temporary test-output locations;
existing dirty evidence remains untouched.

P2's V01 intake proved the expected shared C06 gap: D28 setup remains
`[TARGET]`, there is no public onboarding-access renewal command, and active
drivers are excluded from password recovery. The controller therefore grants
P1 a serialized shared-integration sub-lease after its current safe point:
implement only (a) a public, non-enumerating, rate-limited onboarding-access
renewal request using the exact stored recipient and existing provider-neutral
outbox; (b) D28 digest-only, short-lived, single-use, superseding admin-issued
setup authority whose completion rechecks approved/current evidence, consumes
setup and prior onboarding authority, activates the invited driver and rotates
session authority; and (c) password reset eligibility for active drivers only.
This sub-lease includes the directly necessary migration/model, auth/admin
routes and schemas, driver-application/onboarding service calls, existing typed
notification builder/template wiring, generated contracts/native fixtures and
focused tests. It does not authorize a notification redesign, provider call,
new recipient source, new policy value, or changes to P2-owned UI/tracking/
earnings files. P1 signals contract stability; P2 then owns driver-flow
integration verification. Required evidence covers known/unknown request
parity, exact-recipient and rate-limit behavior, rejected/expired/superseded/
replayed setup denial, duplicate convergence, unchanged D30/D31 behavior,
pending-driver reset denial, active-driver reset success, replay denial and old
session revocation.

P1 reports the C06 backend/generated contract stable after focused setup,
renewal, OpenAPI, audit-route and frontend type checks. The controller now
leases P2 only the public driver-facing `frontend/src/app/driver-account-setup/**`
route and directly related apply/status entry points and tests to consume the
settled contract. P1 retains backend/auth/generated ownership and must not edit
that new frontend route concurrently. P2 must preserve generic renewal
responses and provider-neutral/fail-closed delivery wording, then include the
complete recovery flow in its real-backend desktop/mobile verification.

**Phase-I admission (14 Sep 2026):** P1 and P2 are `COMPLETE` as uncommitted
integrated candidates. P1 closes C02–C04, advertiser V01/V06, advertiser C14/
C15 and the serialized C06 backend/generated/shared-recovery contract. P2
closes C05–C08 and driver V01/V06. Evidence includes exact quotation and two-
cycle campaign-change real-stack journeys, desktop/mobile driver recovery,
209-test P2 and focused P1 frontend suites, PostgreSQL change/setup/migration/
stored-file idempotency checks, type/lint/build/contract checks, and truthfully
reported environment skips. Independent P2 specialist re-review and integrated
Sol High consolidated money/security/privacy/tracking review both PASS after
fixing concurrent setup initiation, offline queue wording, currency-neutral
empty earnings, past-end pagination, lost artwork-confirm recovery, sequential
change request identity and D28 architecture truth. P3/P4 may now plan against
the settled Phase-I contracts; Phase-I files remain frozen except for a
review-proven integration correction returned to their original owner.

Phase II uses two Sol High owners after one independent aggregate plan review.
P3 exclusively owns non-money operator discovery and workflow surfaces:
admin shell/search, users/drivers/vehicles, applications, approvals,
assignments, fraud/display/late-data, traffic, measurement, contact and
non-money closeout views plus their scoped read projections and domain tests.
P4 exclusively owns payout batches, eligible-line selection, debt/corrections,
maker-checker approval, provider-neutral submission outcomes, reconciliation,
billing settlement projections and money tests. P4 may consume the settled
driver payment contract but must not edit Phase-I driver/apply files; P3 must
not edit payout/billing/money services or screens. Shared generated contracts,
admin shell/common search primitives, audit fixtures, seed/test harnesses and
cross-domain closeout state serialize through a controller-recorded lease;
neither owner may infer ownership from convenience. P3 resolves V02 and the
non-money portion of V03/V06 before adding a new queue; P4 resolves the money
portion of V03/V06 before extending payout flows. Both preserve existing
commands and atomic authority, use named human context instead of raw IDs,
provide red/green and real-backend desktop/mobile evidence, and retain every
external provider/legal/physical-operation gate.

Phase-II independent Sol High plan review returned `FIX`; the controller adopts
all four amendments before dispatch. Phase I is now the local baseline commit
`f56d7fb`, excluding the pre-existing test-result/audit/archive artifacts that
remain uncommitted. P3 initially holds the serialized lease on generated API/
frontend/native contracts, API-router/model registration, migration numbering,
architecture placement/changelog, authorization/audit-route inventories and
admin shell/common search. P4 first builds contract-neutral payout queries,
services and tests and submits exact route/schema needs. After P3 freezes and
generates its contracts, the controller transfers this lease to P4; P4 then
adds its route/schema surface, regenerates the aggregate once, and both owners
verify their consumers. Shared seed helpers, `tests/conftest.py` and cross-
domain closeout composition remain controller-leased.

V03 is bounded to read-only closeout readiness and visibility of existing
cancellation, settlement, report, contact and external physical/provider
blockers. Neither owner may add a campaign/assignment `completed` transition,
claim removal or cash completion, or infer missing operations policy. A new
lifecycle command requires separate owner authority. Any composed closeout
page waits until P3/P4 projections stabilize, receives one serial owner and
must not duplicate money calculations.

P3 acceptance additionally freezes a per-queue search/filter/order/pagination/
history/action matrix; general search excludes national ID, bank, raw evidence
and raw GPS. Sensitive reveal requires selected purpose/confirmation, no-store,
auto-hide/DOM removal, exact-current-version audit and stale denial. Activation
readiness is zero-write advisory composition from existing authorities; final
activation rechecks under its existing lock, including ready-then-source-change
denial. Quarantine apply/discard requires confirm, stale/double-submit safety
and never reprices money or mutates/reissues reports. Measurement adds only
list/status/read orchestration over the existing issuer and never renders
absent/incomplete/suppressed/gated evidence as zero or complete. Contact work
preserves verified phone, exact-purpose consent and D35 invalidation.

P4 acceptance additionally requires an advisory eligible-payment projection
with named driver/payee, masked destination, individual credits, debt
deductions, exact currency totals and ineligibility reasons; reservation still
uses immutable IDs and revalidates under existing locks. Paginated batch
summary is separate from bounded responsive detail with maker/checker names and
per-line outcome/history. Draft-create/reserve has durable lost-response and
multi-tab recovery, exact retry convergence or explicit draft recovery,
all-or-none reservation, stale hold/debt/eligibility denial and concurrent
single-winner evidence. A two-admin browser journey proves maker self-approval
denial, distinct-checker approval, queued-versus-submitted truth, provider-
unavailable/unknown/partial outcomes, same-key retry and verified-line-only
paid finality. Money closeout reports only recorded cancellation settlement,
debt and unbatched/reserved/in-flight/paid facts plus external blockers.

Initial Sol High P3/P4 dispatches failed before producing any work because the
agent pool reported a usage limit. Workspace inspection confirms no Phase-II
product mutation. The controller reassigns the unchanged, independently
reviewed packets to GPT-6 Astra High owners: this is at least as capable for
P3's cross-domain privacy/measurement authority and P4's money/concurrency
boundary, preserves the same two-writer limit and leases, and is a dispatch
recovery only—not a scope or acceptance change.

P3 freezes its additive operator API contracts after OpenAPI drift,
authorization-inventory and audit-route checks. No Phase-II migration/model
registration was needed in P3. The serialized generated/router/schema/
architecture/inventory lease now transfers to P4 for only its approved payout
surface: optional draft request identity, eligible-payment advisory,
paginated batch summaries/detail, bounded line history and an additive optional
campaign scope on the existing money-balance projection with unchanged default.
Static routes precede the batch-ID route; search is allowlisted human identity/
reference only; every amount is a Decimal string with currency; page, filtered
and selected totals are labelled distinctly and no client-computed sum becomes
authority. General selection does not bulk-decrypt bank data; an explicit
purpose-audited detail may return a mask only. P3 freezes all shared/generated
files and continues only its UI/service/test domains. P4 regenerates the
aggregate once after stabilization, signals P3 for consumer verification, then
freezes the lease. Cross-domain closeout may consume the settled campaign-
scoped balance later; it gains no lifecycle command or new money calculation.
P3 readiness must not treat absence of a pre-existing assignment-liability
reservation as a blocker because final activation may create it. P4 therefore
owns one exact read-only reservation-eligibility projection extracted from the
same calculation/checks used by `reserve_assignment_liability`, with parity and
zero-write evidence. P3 consumes only its minimal result/reason; final
activation remains the sole locked reservation/action authority.

After the aggregate generated contract freeze, the controller grants P4 one
final documentation-only lease on `docs/architecture.md`. P4 must retain its
provider-neutral money placement and incorporate P3's exact operator placement
packet: safe named search and focused current-evidence review; paginated
creative/assignment preparation and zero-write readiness; existing-engine
measurement discovery; late-data and current-consent contact consumers; and
read-only closeout boundaries. The changelog must state that no new issuance or
money engine, lifecycle completion, provider call, deployment or native-device
evidence is added. This lease does not reopen generated contracts, schemas,
router registration, migrations, inventories or either owner's product files.

P4 browser verification resolves the packet's retry wording against existing
authority: same-key idempotent retry applies to an ambiguous submission before
terminal resolution. A terminal failed payout line is not retried in place; it
requires a newer verified bank version and creates a new immutable replacement
batch/line linked to its predecessor, while an unchanged destination remains
denied. P4 must present and test both paths distinctly and consume the returned
replacement identity; the existing payout engine is not weakened to satisfy an
overbroad “failed-line same-key retry” phrase.

Phase-II specialist review returns P3 to `FIX` before admission. Terminal
application history/detail must use the full existing application-status type
while the default queue remains pending-only; approved/rejected history must
serialize without writes. Approval-document downloads must enforce current
linked person/vehicle evidence from server authority rather than caller reason
prefixes, deny stale/unlinked files before presign/audit, and return
`Cache-Control: no-store`; separately authorized historical/security reads
remain unchanged. Three named P3 admin pages require formatter-only cleanup.
The review also could not audit the ephemeral `/tmp/mobility-p3-*` logs, so
controller admission relies only on reproducible commands/results or retained
evidence. A separate Phase-I D28 correction must make guessed nonexistent
account-setup resources return the established 404 without changing real
ineligible 409 or setup/idempotency semantics; its exact security plan requires
independent PASS before editing.

Phase-II money specialist review also returns P4 to `FIX`. Terminal replacement
must compare canonical bank destination identity—not version UUID—so key rewrap
or identical recapture cannot satisfy the changed-destination gate. Replacement
creation must preflight every trip's current successful assessment before any
line is built, retaining all-or-none behavior. Campaign closeout must derive
active provider exposure from scoped payout-line chains independently of ledger
availability: economic `cash_paid` remains separate, while an additive Decimal
`provider_verified_paid` field exposes actual verified provider successes and
reserved/in-flight values retain unresolved replacement exposure. P3 owns the
generated/schema lane until its review fixes freeze; P4 implements contract-
neutral corrections meanwhile, then receives one serialized aggregate contract
lease. Rewrap/identical recapture, one-stale-trip multi-line rollback, late
predecessor success with unresolved replacement and dual-success cases require
red/green PostgreSQL evidence and independent re-review.

**P4 takeover and Phase-II admission (14 Sep 2026):** The owner reassigned the
interrupted P4 correction and remaining programme to one direct Claude Opus 5
High controller in this checkout; the owner later lifted the no-subagent limit,
so independent read-only reviewers ran on Opus 5 after the Fable reviewer pool
reported a usage limit. The interrupted bytes were inspected rather than
trusted. Each money finding was reproduced red on PostgreSQL by temporarily
removing only its correction, then restored byte-identically: disabling the
bank code/account-number comparison let rewrap, identical and name-only
recapture replace a failed line; removing the preflight let a two-line
replacement with one stale trip assessment succeed; ledger-derived exposure
reported `in_flight` 0.00 instead of 100.00 after a late predecessor success.
All pass with the corrections. Added explicit changed-destination success
(new version and key, destination differs, convergent retry). Focused money and
concurrency suites: 24 files, 235 PASS, zero skips; the six replacement-review
tests PASS. Independent money re-review: PASS, all three findings closed; it
notes that replacement identity needs the predecessor version's original key to
remain in the keyring (fail-closed liveness only) and that all-or-none
replacement applies per batch.

Consolidated independent Phase-II review returned `FIX` with no authorization,
tenant or sensitive-disclosure defect. Corrections: advisory readiness now
reports `ASSIGNMENT_ALREADY_ACTIVE` before other prerequisite checks instead of
inviting a second activation (red then green; final activation replay
unchanged, DEACTIVATED reactivation unchanged); every administrator file
download returns `Cache-Control: no-store` (red then green); formatter cleanup
applies only to files clean at baseline plus new files, with `ruff check .`
green. Controller disposition: current-version NIN/bank enforcement remains
scoped to the approval purpose because other purpose-audited historical reads
are preserved by this packet. Non-blocking notes retained without code change:
readiness takes the same locks as final activation, detail-page 404s reach the
generic error page, eligible-payment reads are per-row bounded queries,
formatting-only hunks remain in two pre-dirty files, the fraud spot-check form
still accepts raw assignment/trip IDs, and vehicle file checks bind to the
vehicle's latest submission.

Integrated real-backend evidence on the final source: an isolated Compose API,
PostGIS, Redis and MinIO project migrated through `0089` with the demo seed,
plus a production build of the current frontend. New read-only
`frontend/e2e/operator-workflows.spec.ts` passes 8/8 on desktop and mobile: named
driver/vehicle/assignment search, already-active readiness, preparation
blockers without an activation control, non-zero empty evidence queues, payout
ineligibility reasons and closeout facts, with no horizontal overflow. A
synthetic two-admin money journey used a fake adapter injected only into a
scratchpad harness server on a fresh migrated database, desktop maker with a
390px checker. It passes selection with held/debt credits disabled, a masked
destination, lost-response multi-tab recovery (one batch, two lines), maker
self-approval denial, provider-unavailable and queued-not-submitted states,
provider-unknown recovery with unchanged line keys, and a partial outcome. It
also denies identical and name-only replacement with no new batch. A changed
destination creates one convergent replacement needing independent approval.
With the replacement still unresolved, a late predecessor success shows
100.07 exposure, 125.10 verified and 125.10 ledger paid; after the replacement
also succeeds it shows 0.00 exposure, 225.17 verified, 125.10 ledger paid and
100.07 driver-wide debt, with no completion claim. Other checks: the combined
P3, authorization, audit-route, OpenAPI, KYC/file, contact, measurement,
setup and payout-projection PostgreSQL run passes 282 tests with zero skips.
The full frontend Vitest run exposed load-dependent races in the new payout form
tests, which queried async preview and recovery controls synchronously. After
switching them to awaited queries with unchanged assertions, the full suite
(127 files, 835 tests, including the R14-B tracker and queue fixtures) passes on
three consecutive runs. ESLint, TypeScript and the production build pass; the
OpenAPI check and regenerated client types are byte-identical. Consolidated
re-review of these corrections: PASS. Evidence stays
under the session scratchpad and is not committed. Stale-hold draft recovery was
browser-proven by the interrupted owner before these corrections and is
retained by the PostgreSQL reservation suites, not re-run in the browser.

**P5 client PRD (14 Sep 2026):** `docs/product-requirements.md` is the
standalone client-readable requirements document. It reconciles the prior
prompt-09 draft and its adversarial review with adopted decisions, architecture,
the external prerequisite register and the final advertiser, driver, operator
and money implementation. The GPT-6 product-completion blueprint text itself is
not stored in the repository; its admitted scope is taken from this ledger's
programme record. Main requirements carry no audit IDs or status notes and use
four categories: implemented provider-neutral behaviour, conditional or
external gates, pilot scope and post-pilot scope. Traceability to decisions and
register entries sits in an appendix; claims that could not be confirmed in code
are worded as not confirmed. The draft was written by an Opus 5 documentation
worker. Independent review returned `FIX`: duplicate-success debt and
already-active readiness were missing, and ten wording and scope items needed
correction. The controller applied all twelve and independent re-review
returned PASS. The PRD adds no product decision, invented value or live-use
claim. Open owner decisions and external dependencies are listed in its §13.

**P6 acceptance preparation (15 Sep 2026):** Measured against origin
`533f62d`, the push range would have failed the changed-code coverage gate:
frontend 68.3% lines / 54.6% branches; a local backend run of 789 relevant
PostgreSQL tests covered changed lines 90.5% / branches 76.4%. Behavioural
tests were added for zero-coverage operator pages and actions, payout failure,
debt and destination-mask paths, advertiser preparation/actions and password
recovery pages, with no product, config, skip, timeout or floor change. Two Opus
test workers stopped on a usage limit; the controller validated and completed
their files. Independent review returned `FIX` for load-dependent races and
four weak assertions, and all were corrected. Result: local changed coverage
across the push range is frontend 92.2% / 87.4% and combined 91.4% lines /
85.3% branches, above the 90/80 floors, with the local backend figure a lower
bound. Full frontend Vitest runs 143 files / 980 tests: two stress runs were
green; one had a single timeout in an unchanged driver-application upload
test, which passes in isolation. Dependency triage: `next` and
`eslint-config-next` move 16.2.10 → 16.3.5, fixing proxy-bypass,
server-action, SSRF, cache-confusion and image-optimizer RCE advisories.
Non-forced audit fixes clear all high findings. Residuals: `maplibre-gl` needs
major v6 (no application HTML sink; revisit with the basemap gate), and
dev-only Vitest 4.1.10 stays pinned to avoid coverage instrumentation drift.
TypeScript, ESLint, production build, Ruff, OpenAPI drift and progress
validation pass. Environment isolation: config, demo-seed, pre-production,
health, CI-authority and R59 contract guards run without a database show one
dependency-only gap. The 91 `test_w403a_release_preparation.py` failures there
require the configured integration database, as CI provides; they are not
claimed as local evidence. Full ordinary E2E with the upgraded framework was not
re-run locally. Exact-SHA CI is the acceptance gate, and physical-device,
provider, legal and deployment gates remain external.

**P6 exact-SHA CI corrections (15 Sep 2026):** Runs on the pushed programme
exposed integration gaps, each reproduced locally before correction:
- The release environment contract omitted the account-setup URL and TTL;
  examples and production Compose now carry a blank URL live-use gate and the
  code default TTL.
- The architecture inventory and two migration-head pins still named `0088`.
- A frozen-window concurrency test predated preview-then-confirm changes.
- The driver tracker labelled healthy buffering between sends "Waiting to send";
  that state now requires an unconfirmed session. The W4-03B mobile journey was
  red, then green, on a fresh synthetic mock.
- The W4-03B backend path inserted a payable credit for an unassessed trip, so
  payout reservation correctly refused it; the fixture now runs real replay and
  assessment stages.
- Backend critical coverage fell 16 lines and 18 branches below the exact
  baseline ratio. CI does not count backend code reached through the HTTP test
  client, so direct service tests were added for campaign-change refusals,
  named search, application filters, generic renewal, draft conflicts, stale
  KYC downloads, campaign-create retries and creative resubmission.
- With every ratio above baseline, D33 required a controlled baseline refresh
  for the 35 added eligible sources and the Next.js lockfile. The checker's own
  refresh mode under Python 3.12 adopted run `34946893485` measurements. Every
  adopted global and critical ratio is at or above the prior receipt; a clean
  simulated gate passed on the refresh commit.
- CI path filters exclude `coverage/**`, so a baseline-only commit starts no
  run; exact-SHA acceptance must follow a docs, source or test change.
- Exact-SHA run `35074771398` on `024a312` passed frontend checks, all six
  backend shards, backend aggregate, R59 and desktop/mobile E2E. Its measured
  coverage exceeded every adopted ratio after deterministic seed-command and
  seed-safety tests replaced manual-only coverage; the gate then correctly
  required a metadata refresh for the changed test inventory. The controlled
  D33 receipt was regenerated from that run's backend/frontend artifacts under
  Python 3.12 without lowering any floor. One final exact-SHA CI run remains
  mandatory for acceptance.
A separate concurrent CI-throughput edit to `ci.yml`, its authority test and
this ledger belongs to another owner and is not included.

**CI submission-reference test correction (14 Sep 2026):** Owner “fix it pls” authorizes this bounded continuation in the existing master checkout after run `34842765201` on `e952341` failed only the ordinary desktop/mobile submission-history assertion. Sole writer is this CI task; controller is idle. Align the stale `Submitted snapshot SHA-256:` assertion with canonical `Submission reference:` while requiring a 64-character hexadecimal hash; retain approval, immutable history and all other gates. Scope: `frontend/e2e/campaign-flow.spec.ts` and this evidence entry only. Existing owned commit/non-force push authority applies; no product, coverage-floor, skip, provider or package-queue change. Independent Sol Medium plan review PASS. Both unchanged desktop/mobile journeys reproduced the exact missing-label failure locally (`/tmp/cardvert-label-red-real.log`); corrected complete campaign-flow file: 10 PASS, zero retries/skips (`/tmp/cardvert-label-green.log`). ESLint, progress validation and diff checks PASS. Initial existing-preview attempt was stopped because one-click login did not match the ordinary test harness; accepted verification used an exact-source temporary preview with regular login against the existing synthetic backend. Independent Sol Medium consolidated review PASS with no findings; exact pushed CI must finish before closure, with its terminal run linked in the owner/controller handoff without another evidence-only commit.

Coverage follow-through: pushed `10bf582` / run `34850723035` passed frontend, all backend shards/aggregate and R59, then failed the unchanged global line floor: backend 25,289/28,518 versus adopted 25,291; frontend exactly 3,413/5,068 and branches above floors. No source instrumentation or floor changed in the label fix. Compared real artifacts show intermittent indirect async-service hits, including trip summary/count paths. Bounded verification amendment adds a real PostgreSQL trip summary/batch-count regression in `tests/test_trips.py`, asserting empty/populated/replayed counts, timestamps and cross-trip isolation directly in one async test context. No product, floor, policy or skip changes. Independent Sol Medium amendment plan PASS; temporary count-plus-one mutation failed the new empty-trip assertion and was immediately restored (`/tmp/cardvert-label-trip-red.log`). Full trip file: 29 PASS against configured integrations (`/tmp/cardvert-label-trip-green.log`), Ruff PASS. Local LCOV records six lines absent from the failed run; diagnostic union 25,295 exceeds unchanged 25,291 backend floor, but is not claimed as GitHub provenance. Independent Sol Medium consolidated amendment review PASS with no findings; fresh exact-SHA CI remains the completion gate.


**First-phase integrated result (14 Sep 2026):** A/B source frozen; narrow independent Sol Medium reviews PASS including money/measurement semantics and A test-pin amendments. Controller final frontend coverage: 109 files / 753 PASS; first aggregate retained 752 PASS / 1 stale map-copy assertion red, then focused fix green. B read-only real-backend desktop/mobile: 12 PASS after disclosed initial 11 PASS / 1 cold-dev loading timeout unchanged repeat. Remaining controller admin/sign-in/client-validation selection: 24 PASS, zero retries/skips on exact source-copy regular-login preview; initial main :3000 one-click-mode harness attempt invalid (3 locator failures, 1 interrupted, 20 unrun), not product evidence. Progress/diff validation PASS. No commit/push. Coverage-policy admission closed with the producer-compatible Python 3.12.14 runtime and exact accepted backend artifact from run `34790587438`: the controlled baseline receipt was refreshed without lowering adopted floors, and changed coverage passed at 123/123 lines (100%) and 199/220 branches (90.4545%). Evidence A `/tmp/mobility-owner-a-sep14/`, B `/tmp/mobility-b-takeover.78ddo2/b-handoff.md` and `admin-campaign-e2e/`, frontend `coverage/frontend/`. Deferred exact HEAD-identical admin fraud filters overflow: 445px at 375px viewport; no layout patch. Test-dataset isolation, commercial error URL handling, broader tracker/legal/journey/planning copy and external deployment/provider/device gates remain outside this bounded result. Initial admin packet current focused 30 PASS and existing independent review fixes retained; full mutating campaign/native/production-CSP rehearsals not claimed by this first-phase verification.

**Combined verification correction (14 Sep 2026):** frontend coverage run on stabilized A/B: 752 PASS / 1 stale shared-copy assertion failure in campaign map test. B additionally leases only `frontend/src/app/advertiser/campaigns/[campaignId]/map/page.test.tsx` privacy-message assertion to follow changed shared zone copy; retain no-geometry/no-map/no-sensitive-zone assertions. No map implementation or disclosure behavior edits. Controller reruns aggregate after focused correction; original run remains explicitly red.

**Login selector parity (14 Sep 2026):** canonical customer CTA `Sign in` requires directly pinned `Enter the network` selectors to follow presentation. A leases only that string replacement in `frontend/e2e/**` excluding B-owned `driver.spec.ts`, `analytics.spec.ts`, `billing.spec.ts`, `w401d-release-rehearsal.spec.ts`; B aligns excluded files. No other test semantics, assertions or security boundaries change. Integrated browser execution remains required.

**Takeover integration pin (14 Sep 2026):** A additionally owns only the visible metric-string assertion in `frontend/e2e/campaign-flow.spec.ts` to align canonical `Estimated ad exposure`; test behavior/strength unchanged. B's E2E pins remain disjoint. Controller executes integrated browser gates after stable A/B results; pin inspection alone is not execution evidence.

**Codex takeover (14 Sep 2026):** owner requests two GPT-5.6 Sol Medium continuation tasks in this existing master checkout. Model gate confirmed for bounded frontend corrections/verification with unchanged money/privacy semantics and independent final review. Claude B auto-continue verified OFF; A usage-blocked with no auto-continue control present. A owns advertiser overview/detail/layout/login, unavailable/data helpers and only methodology UI assertions; B owns report/commercial/billing/driver/fraud copy and directly affected tests. No overlap with accepted admin approvals/audit, new worktree, commit/push or live actions. Preserve partial Opus work; controller alone owns ledger/integration. Shared resource mutations and aggregate coverage serialize.

**Opus reconciliation correction (14 Sep 2026):** A/B initial receipts received; acceptance remains pending. Core owner-rejected measurement jargon survived due to pinned tests, which do not override plain-language product direction. A resumes narrowly to simplify overview/detail exposure and internal diagnostic presentation while retaining actual semantics; additionally leases `frontend/src/app/login/page.tsx` for Abuja-only sign-in copy and only UI-string assertions in `tests/test_measurement_methodology.py`, preserving false-claim/formula safeguards. B's report presentation follows the same agreed semantics without backend identifier/export changes. Final browser checks must use stabilized source. Test-stack pollution/isolation, commercial error URLs and remaining deferred copy are explicit unresolved dispositions, not silently accepted or cleanup-authorized.

**Opus ownership amendment (14 Sep 2026):** owner requests Opus 5 sessions for production-first correction and plain human-facing language across the product. Two Claude Opus 5 High owners: A takes over the paused Sol advertiser-resilience diff and production/test-data presentation diagnosis; B inventories and corrects human-facing copy outside A's files after review and exact lease. A owns advertiser overview/detail/layout, login presentation, shared unavailable component and advertiser helpers/tests; B cannot edit those, backend semantics, contracts, shared primitives or accepted admin packet without explicit controller lease. Preserve current resilience and unrelated changes; no synthetic-to-live relabeling, destructive data cleanup, safety-gate bypass, commit/push or new worktree. Independent plan and post-build reviews, truthful metric meanings and desktop/mobile checks required. Original Sol owner stopped; no duplicate implementation owner.

**Owner correction — production-first presentation (14 Sep 2026):** the first-phase shared packet must build the actual production-facing product, not add demo-account banners, synthetic campaign badges or demo-specific presentation machinery. Remove only newly introduced demo presentation after identifying its exact diff; retain healthy-section resilience, concise capability-local unavailable states, real available data and unchanged sensitive-action gates. Never relabel test/seed data as live or hide/delete records to manufacture readiness. Test data isolation and later integration adapters require explicit scoped preparation before edits. Shared packet acceptance is held pending this amended presentation contract and focused re-verification; earlier demo acceptance is superseded.

**First-phase product file leases (14 Sep 2026):** CI owner released the freeze after all 12 final-revision jobs passed at `1f9229c`. Claude Opus 5 High preparation and independent plan review PASS received from owner attachment `67e3edc0-9b5d-4c49-abea-7eb587eddbaa/pasted-text.txt`; cleared to implement only the seven existing approval/audit files and four colocated additions listed in that receipt. No shared primitives or server actions. Shared Sol High owner is plan-review-only pending independent review, with proposed advertiser overview/detail/layout, presentation-only demo login, and their narrowly required shared unavailable-state/data/demo helpers. Controller alone edits this ledger. Separate browser ports required: Sol owns :3000; Claude must use another free port. No commit/push authority; at most two product writers. User supplies Claude callback.

**Terminal CI acceptance receipt — 14 September 2026:** software commit
`932c2f7cdb6f698f933d14a2bf82ffe96ac145be` is accepted by
[GitHub run 34789268818](https://github.com/oluwasolaonigbinde/mobility/actions/runs/34789268818).
All 12 jobs passed: frontend quality/build (656 tests), backend static, all six
backend shards, aggregate, changed-code coverage, R59 (1 real-stack test), and
ordinary desktop/mobile E2E (96 passed, the 18 individually justified skips below,
no failures or flaky retries). All 2,812 backend test identities executed exactly
once with zero skips; downloaded JUnit/coverage hashes, full collection identity,
source SHA and regenerated aggregate receipt match GitHub producer provenance.
Actual GitHub coverage exceeds the adopted receipt: backend 25296/28518 lines,
4636/6770 branches; frontend 3247/4977 lines, 2736/5442 branches. Backend aggregate
completed 1,088 seconds after workflow start (18m08s), versus the earlier 69–76
minute serial backend executions. Coverage eligibility, changed-code requirements,
financial rules, native privacy snapshot protection and provider boundaries stay
unchanged. Independent Sol/medium consolidated and specialist review is PASS.

The earlier inference that isolated local passes proved a runner/environment
cause was too strong. Latest Caddy failures were a missing cold-runner image;
coverage above a receipt was wrongly rejected by hit-count equality; a missing
rendered fraud row was silently skipped; and two reproducible product lock cycles
were hidden by serial browser execution. The corrected cycles are campaign-change
FK insertion versus snapshot parent locks, and fraud/recovery scopes versus
snapshot row locks. The exclusive existing reconciliation gate introduces global
snapshot serialization; no tenant-local throughput or deployment-readiness claim.

This closes the CI continuation and its throughput obligation without restarting
R01–R60 or moving `PKG-03 / W2-01C`, which remains blocked only by
`EXT-PAYMENT-PROVIDER`. Legal/privacy, provider credentials/custody, approved report
methods, physical-device, deployment and live-pilot evidence remain external.
The terminal receipt commit is also checked through all CI gates before the
controller callback releases the product-write freeze; its run is linked in that
callback. This receipt references the accepted software commit, not its own
containing commit. Unrelated owner files and the separate admin-UX ledger row
remain preserved and unstaged.

Local verification stabilized (14 Sep): 172 real PostgreSQL/reporting/privacy/
recovery/reconciliation tests PASS; 127 CI-authority/policy tests PASS; eight real
Caddy/CSP browser cases PASS; the original missing shard's 463 tests PASS under
Python 3.12. Fresh one-worker and five-worker real-stack browsers each: 96 PASS,
18 conditional skips, zero failures/retries. Ruff, frontend lint/typecheck, runtime OpenAPI drift,
pre-production static checks, progress validation and final diff checks PASS.
Controlled D33 refresh and verification PASS: changed eligible lines 4/4,
backend 25279/28518 lines and 4623/6770 branches; frontend 3247/4977 lines and
2736/5442 branches. Floors only ratchet upward. Sol/medium consolidated and
money/privacy/security/concurrency review found no substantive implementation
finding; final GitHub acceptance is recorded in the terminal receipt above.
All 23 entry-state user/review files remain hash-identical. The controller's
later admin-UX authorization row remains an unrelated unstaged ledger change.

Ordinary E2E retained skips (18 explicit cases, not exercised behavior):

| Specification / case | Skipped project(s) | Required boundary |
| --- | --- | --- |
| `auth.spec.ts` — admin-created driver changes password inside the driver PWA scope | chromium | mobile driver scenario |
| `auth.spec.ts` — admin-created advertiser must replace the temporary password | mobile-chrome | desktop portal scenario |
| `auth.spec.ts` — repeated login failures surface the 429 retry message | mobile-chrome | one project only — the IP and global buckets are shared |
| `correction-offline-evidence.spec.ts` — lost End response drains the current deferred batch before reconciliation | chromium, mobile-chrome | requires the bounded local P07 fault fixture |
| `correction-offline-evidence.spec.ts` — visibility completion and late GPS callbacks cannot cross the frozen End | chromium, mobile-chrome | requires the bounded local P07 fault fixture |
| `correction-offline-evidence.spec.ts` — partial acknowledgement remains encrypted and settled across reload | chromium, mobile-chrome | requires the bounded local P07 fault fixture |
| `correction-workflows.spec.ts` — person-payee replacement after failure uploads the selected file | chromium, mobile-chrome | Explicit synthetic workflow fixture only |
| `correction-workflows.spec.ts` — vehicle replacement after failure uploads the selected file | chromium, mobile-chrome | Explicit synthetic workflow fixture only |
| `correction-workflows.spec.ts` — campaign attachment recovery survives reload without another campaign | chromium, mobile-chrome | Explicit synthetic workflow fixture only |
| `evidence-verification.spec.ts` — ops queues a physical check and sends failure into the fraud hold | chromium, mobile-chrome | synthetic assignment and trip IDs are required |
| `notifications.spec.ts` — advertiser changes the shared email preference while in-app stays mandatory | mobile-chrome | serialize the persistent preference mutation |

Consolidated continuation evidence (14 Sep, before push): latest failure was an
absent cold-runner Caddy image; five backend shards and R59 had already passed,
so their downstream skips were unexecuted gates, not passes. Older failures span
Python coverage-runtime mismatch, receipt hit-count equality, nondeterministic
coverage paths, missing synthetic E2E authority, shared browser fixtures and
container registry denial. Serial browsers alone did not prove concurrency:
a real dashboard/change deadlock was reproduced and corrected below. A second
five-worker run exposed approval-test reload before mutation completion; await
the visible completion before the existing reload/persistence assertion.

Additional Sol/medium policy review PASS: normal v3 source-changing receipts
still adopt measured floors. Subsequent measurements may improve, but must meet
both trusted and adopted exact ratios; metric counts/percentages/totals and all
immutable provenance fields remain validated. Legacy D36 reconciliation stays
unchanged. Above-floor receipt-equality regression was observed red then green.
No coverage floor, changed-code requirement, source eligibility or instrumentation
was lowered. Current local coverage is explicitly a source-bound diagnostic
composition: five 13da317 GitHub artifacts plus the completed missing shard for
unchanged files, and fresh Python 3.12 tests solely for the two changed
modules (campaign changes and disclosure). It is not relabeled as final candidate shard evidence; exact-SHA GitHub
execution/coverage artifacts became the authoritative closure evidence above.

Second concurrency correction reviewed by Sol/medium: the real snapshot/fraud
cycle is trip-row then fraud-advisory versus advisory then row. Merely moving
trip advisories below campaign rows would still deadlock confirmed-fraud
recovery on its campaign FK. Reuse the existing **exclusive** fraud reconciliation
gate before snapshot parent/contributor locks, preserving every native snapshot
lock and campaign-terms-before-gate order. This serializes snapshot transactions
across tenants and fraud/money reconciliation; no tenant-local throughput claim.
All eight service call sites were inspected for prior shared-gate/row ownership.
Verify both orders, dismissal/confirmed recovery, reconciliation, rollback/retry
and existing privacy phantom protection before final acceptance.

Product correction admitted by Sol/medium privacy/money/concurrency review:
real concurrent dashboard and campaign-change calls deadlock because disclosure
locks organization then campaign, while change insertion holds campaign then
requests the organization FK lock. Pre-acquire that existing organization
`FOR KEY SHARE` protection after advertiser authorization and the campaign
terms advisory, but before campaign row locks; preserve disclosure snapshot locks and all financial rules.
Verify bounded PostgreSQL writer/reader ordering, rollback, exact retry and
uniqueness, then repeat browser concurrency and ordinary acceptance.


Plan amendments accepted by the same Sol/medium reviewer: provision ordinary
E2E's implicit MinIO dependency from the identical Quay digest; refresh the
workflow-bound coverage receipt through D33. For an identical v3 source hash,
inventory, runtime and named-critical membership, preserve the adopted metric
floors during metadata-only refresh while still checking actual measurements
against every floor. Changed sources retain the ordinary ratchet. This removes
incidental race-path high-water marks from infrastructure-only receipt updates;
it introduces no tolerance, floor reduction, exclusion or legacy reconciliation.


CI acceptance continuation contract (13 Sep): **Review-Required** for CI authority,
shared-state concurrency and CSP security evidence. Sole writer Astra/high;
independent reviewer `ci_review` is Sol/medium as explicitly authorized by owner,
review-only for the plan and stabilized integrated diff, including applicable
security/concurrency boundaries. Existing CI workflow is the entry point.
Correct demonstrated dependency/cache failures and verify shard **execution**
against planned inventory using existing pytest reports, then validate combined
coverage and ordinary real-stack browsers. Keep test inventory/assertions,
D32/D33/D36 floors, isolation, product authority and external gates intact.
Any demonstrated product defect receives a concrete amended review packet before
editing. Acceptance requires regression red/green, real integration evidence,
no actionable review finding, and frontend/backend/coverage/R59/ordinary E2E
passing on one exact pushed revision. Owner already authorizes implementation,
owned commit and fast-forward push; no new approval gate is inferred.


| Date | Item | Authority | Scope boundary | Queue effect |
| --- | --- | --- | --- | --- |
| 23 Sep 2026 | **Reconcile current Cardvert issue state after the laptop theft and fix confirmed, admissible issues CV-01–CV-17.** | Direct project-owner request in this session, 23 Sep 2026 | Matrix `issues/planning/current-state-reconciliation-2026-09-23.md`. Owns only the CV-01–CV-17 surfaces named in the narrative above: disbursement claim authority; organization membership service/model, migration `0090` and integrity registration; evidence-verification list filter; report cohort cost indexing; contact-task list query; notification types/feed/email templates and their campaign/creative/quotation triggers; the three §9 contract baselines; the named advertiser campaign files plus `lib/campaigns/schema.ts`, `campaigns/new/actions.ts` and `wizard.tsx`; the `audience.py`/`disclosure.py` membership consumers and the two conflicting membership fixtures; driver home/profile, admin fraud, theme-switcher, Dispatch CSS and notification-centre frontend files; `tests/conftest.py` and migration-test database helpers; README test instructions; the runbook D29 company-move section; architecture placement/changelog; this ledger and the matrix; and, only after the first exact-SHA CI run of the owner-approved push, the controlled D33 refresh of `coverage/baseline.json` from that run's artifacts. | Review-Required bounded batch outside the 71-item queue. Does not move the `PKG-03 / W2-01C` external-provider pause, clear any external gate or change any owner decision. |
| 16 Sep 2026 | **Integrate the owner-approved Terrax company landing design at the Cardvert public root and admit visual directions 10 “Dispatch” and 11 “Ledger” into the live product theme switcher.** | Direct project-owner request in the active integration task, 16 Sep 2026: make the Claude landing page the actual system landing page, connect its CTAs to Cardvert, and make both new directions live | May replace the root redirect with a public, CSS-isolated landing surface; make `/landing` a compatibility redirect; map driver conversion to `/apply`, existing-user access to `/login`, and advertiser acquisition to the official Terrax contact address; integrate only the reviewed Dispatch/Ledger registry, scoped CSS, tests and design documentation. `sites/terrax-media/**` is source-only and must not be shipped as a duplicate app. Existing role homes, auth authority, directions 1–9, status borders, APIs, data models and provider/live-use gates remain unchanged. Owns `frontend/src/app/page.tsx`, the compatibility `/landing` route, a namespaced landing component/style/asset surface, theme registry/CSS/tests, `docs/design/**`, architecture placement/changelog and this row. | Review-Required bounded frontend integration outside the 71-item queue. It does not move the `PKG-03 / W2-01C` external-provider pause or clear any external gate. Exact-SHA run `35093510970` passed frontend/static checks, all six backend shards and aggregate, R59, and ordinary desktop/mobile E2E; its sole failure was the coverage receipt's stale parent binding. The reviewed metadata-only receipt now binds that unchanged evidence to parent `8e3ce9d`; final exact-SHA CI remains required. |
| 14 Sep 2026 | **Five-stream product build, first phase: shared resilient pages/demo foundations alongside bounded Claude admin UX.** | Owner: “just orchestrate the firsty phase of the work”; two disjoint owners approved | Sol High owns shared unavailable-state/error presentation and advertiser section-level resilience using existing APIs/demo capabilities; Claude Opus 5 High exclusively owns admin approvals and audit pages. No auth, backend, contracts, CI, coverage-policy, live-use gate bypass, provider calls, commit/push or new branch/worktree. Controller obtains one independent plan review and consolidated post-build/privacy-boundary review; red/green and real browser evidence required. User supplies Claude completion; no Claude polling. CI freeze released by terminal owner callback at `1f9229c`. Exact shared owner file lease is fixed after read-only preparation before product edits. | First phase ACTIVE outside the package queue; PKG-03 external pause unchanged. Later advertiser, driver and specialist streams remain pending, not dispatched. |
| 13 Sep 2026 | **Bounded admin-UX delivery through Claude Opus 5 High alongside CI diagnosis.** | Direct owner approval “go ahead, pass it through opus 5” | Opus 5 High prepares and reviews approval pagination/action-pending states, installation evidence viewing, and audit-filter labels using existing APIs. Product writes wait for the controller-confirmed exclusive lease with CI owner `01a09cdc-9ae6-70e0-b967-93d3da979bdc`; no shared primitives, backend, contracts, CI, coverage-policy, payout logic, commit or push authority. Preserve unrelated files and freeze product writes during exact-SHA acceptance. | Bounded side delivery; no reprioritization of the package queue. Controller owns ledger updates and final admission. |
| 13 Sep 2026 | **Resolve recurring integrated CI failures end to end.** | Direct owner request in task `01a09cdc-9ae6-70e0-b967-93d3da979bdc`; sole Astra/high implementation in existing `master`, one Sol/medium review-only agent, bounded non-force commit/push authorized | Investigate and correct demonstrated causes across product, fixtures, isolation/concurrency, runtime/dependencies, coverage, sharding, workflows and real-stack browsers. Preserve D32/D33/D36 floors and test authority, unrelated review sources and protected provenance; no deployment/live-provider operations. | Continuation DONE at `932c2f7` / run `34789268818`; PKG-03 external pause unchanged. Entry HEAD and fetched origin/master `13da317087aa5aa7b56bc51aad535bca90547aa3`; predecessor inactive, controller idle. Latest run `34690537163`: frontend/static/R59 and five shards passed; shard 5 failed eight absent-Caddy-image cases, aggregate failed closed, coverage/E2E skipped. Admin-UX controller notified to retain review-only preparation through exact-SHA acceptance. Independent plan/consolidated/specialist review, regression red/green, actual complete GitHub shard execution/coverage proof and every required gate PASS; controller callback releases the write freeze after terminal receipt CI. |
| 12 Sep 2026 | **Remove the 69–76 minute backend CI bottleneck before continuing exact-SHA acceptance.** | Direct project-owner instruction to stop repeating the multi-day serial wait and fix the gate itself, 12 Sep 2026 | May change only the CI backend-test topology, deterministic shard selection/coverage aggregation, their contract tests, the already-required deterministic driver-greeting regression, and this evidence record. Every collected backend case must execute exactly once across isolated real-integration runners; zero-skip authority, PostgreSQL/PostGIS, Redis, MinIO, ClamAV, combined LCOV provenance, unchanged R17 floors, quality, R59 and ordinary real-stack E2E remain mandatory. No product/API/schema/migration/provider/live-use behavior or coverage exclusion may change. | Adds a bounded CI-throughput correction outside the completed package queue and does not move the PKG-03 external pause. Six isolated shards plus fail-closed aggregate implemented; independent plan and consolidated post-build reviews PASS. Missing-shard mutation rejected; correctly hashed malformed coverage regression observed red then green after requiring readable, nonempty branch CoverageData. 107 focused tests, Ruff, progress validation, shell/YAML/diff checks, pre-production static verification and frontend lint/typecheck/656 coverage tests PASS. Refreshed collection: 2,780 node IDs in 235 files, balanced 464/464/463/463/463/463. Reviewer retry reconciles the usage-limit interruption. Remaining exact-SHA gate: after push, measure workflow-start-to-backend completion, require materially shorter wall time and all five acceptance gates to execute/pass; no speed or release-readiness claim before that evidence. |
| 6 Sep 2026 | **Execute the reviewed post-remediation correction programme, C01–C37 and H07.** | Owner's exact `APPROVE IMPLEMENTATION OF THE REVIEWED PACKETS` in the existing Astra controller, following aggregate contract V3 plan-review PASS and the frozen two-macro-phase execution amendment | The existing Astra controller implements directly; no implementation subagents or initial handoff. Exactly two further Sol/medium review-only subagents: one complete Macro-Phase A review, then one fresh final specialist/consolidated review. This explicit owner amendment replaces intermediate specialist dispatches and earlier concurrency/model preferences for this programme only. No commit, push, merge, deployment or external-system contact is authorized. | Authorizes the bounded correction register below without changing the ten-package queue, original checklist, R01–R60 history or PKG-03 external pause. |
| 5 Sep 2026 | **Adopt R17 Option A: a changed-code coverage ratchet with at least 90% line and 80% branch coverage, plus no regression from exact current global and named-critical baselines.** | Direct project-owner choice “A” in the active remediation controller, 5 Sep 2026 | R17 must select its comparison base deterministically for PRs, pushes and local runs; fail closed to an explicit merge-base rule; exclude generated code, tests, fixtures, migrations, build output and vendor code. It may add only the minimum backend/frontend coverage tooling, policy tests, workflow wiring and a D27(e)-superseding decision row after an independent plan review. It must inventory and reuse existing tooling and must not duplicate R59's real-stack journey or evidence. | Clears the R17 policy block and authorizes read-only R17 planning now. Implementation remains serialized until R59 releases `.github/workflows/ci.yml`; R60 remains dependency-held until both R17 and R59 are accepted. |
| 4 Sep 2026 | **Require an explicit controller callback after every slice, and predeclare compatible multi-slice session lanes where they reduce repeated setup.** | Direct project-owner instruction in the active remediation controller, 4 Sep 2026 | Every controller-created task must call `send_message_to_thread` for controller task `01a05de2-0b5d-73f0-ae3d-0e979b734658` with its terminal receipt; ending only in the worker task is insufficient. One visible task may retain its original model and continue a predeclared dependency-ordered lane only when the slices share a domain, risk class and compatible ownership. It must return a separate receipt after each slice and wait for controller admission plus the next explicit packet. Cross-domain work, overlapping leases, migrations/generated contracts owned elsewhere, or a changed model require a fresh task. | Applies to all current and future controller dispatches. R07 and R50 remain standalone because their successors require different risk/model gates; R18→R19 and R20→R21→R22 are the first compatible reusable lanes. Missing callback delivery triggers one state reconciliation and adoption of existing work, never a duplicate implementation owner. |
| 4 Sep 2026 | **Use fresh visible sessions for new work; use GPT-5.6 Luna/max with fast mode for simple bounded tasks and reserve Sol for genuinely complex work.** | Direct project-owner instruction in the active remediation controller, 4 Sep 2026 | Do not use internal subagents as the execution owner for new slices. Before dispatch, apply the repository model gate to the task's actual hardest boundary: Luna/max fast is preferred for simple low-risk bounded work, Terra remains available for ordinary implementation, and Sol is used only for difficult money, security, migration, concurrency or cross-contract authority. Never reuse an older session under a changed model. | Applies to all future dispatches. Existing completed reconciliation workers are closed; R03 and R48 must begin in separate fresh visible sessions with proportional verification and terminal-only callbacks. |
| 4 Sep 2026 | **Use otherwise-idle disjoint capacity for the smallest verified controller-audit follow-up while the main remediation frontier is dependency-held.** | Direct project-owner instruction to maximize useful parallel execution, 4 Sep 2026; controller-selected FU-06 from the recovered row-385 audits | FU-06 may verify and, if current, correct mobile-width reachability of existing logout and change-password controls only. It owns the shell/account-control component and focused responsive tests; AUT-004 logout/session semantics, APIs, schemas, routes, generated contracts, R36/R37, R47 and user-owned design/theme work remain unchanged. | Adds one bounded side packet outside R01–R60 without moving the active PKG-10 pointer. Its exact disjoint lease and proportional verification must be recorded before dispatch. |
| 3 Sep 2026 | **Controller orchestration must not absorb or interfere with Claude tasks created independently by the owner.** | Direct project-owner correction in the active remediation controller, 3 Sep 2026 | Session reconciliation covers only tasks explicitly dispatched by this controller. Driver-journey, landing/design, future-delivery, external-dependency and other owner-created Claude work remain outside controller inspection, mutation, admission and scheduling authority unless the owner later places a specific result in scope. | Narrows the result-recovery task to the three controller-dispatched row-385 audits; the broader prepared Claude prompt was not sent. |
| 3 Sep 2026 | **Dispatch approved Claude Opus 5 High work immediately in fresh tasks; do not reuse old tasks or request a redundant model/send choice.** | Direct project-owner instruction in the active remediation controller, 3 Sep 2026 | The controller still applies the repository model gate, dependency graph, exact lease and no-duplicate checks before dispatch. Once a bounded Opus packet is approved by those controls, create a fresh Opus 5 High task and send it directly. Terminal-only callbacks remain required. | Applies to future Opus dispatches. It does not authorize dependency bypass, overlapping writes, or duplicate work. |
| 2 Sep 2026 | **Do not reuse an old task with a different model for new work.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | A visible task retains the model family selected when it was created. Related continuation may reuse it only without cross-model reassignment. When new work requires another model, create a fresh visible task with that model selected before dispatch, preserving cache efficiency and clear evidence provenance. | Applies to every future remediation and side-programme dispatch. The four V11–V14 correction packets were already created as new tasks directly on their chosen Terra/high or Sol/high models. |
| 2 Sep 2026 | **Launch the paused UI/product-review suite with 3–5 Claude Opus 5 High sessions as soon as the moving UI surfaces stabilize.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Trigger only after R11→R14 and R39→R44 are accepted and no overlapping auth, advertiser-planning, reporting, privacy-state, frontend, or generated-contract bytes remain unadmitted. The canonical programme is `issues/product-ui-review/README.md`; prompts 2, 3 and 5 are answered, while 1, 4, 6–8 and sequential 9–11 remain. They remain read-only and use terminal-only callbacks. | Durable side obligation; it does not interrupt or overlap the active remediation writers. Continue the remaining prompts in the canonical folder's documented order and reconcile every answer there. |
| 2 Sep 2026 | **Use terminal callbacks instead of routine progress narration.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Future sessions send one brief start acknowledgement, communicate only a genuine authority/scope blocker, and send one terminal completion callback. The controller does not poll or consume routine progress prose; admission remains based on the terminal receipt plus direct inspection of repository bytes, tests, reviews, and integration state. Current sessions were already instructed directly by the owner and are not messaged again. | Reduces token and attention overhead without weakening verification, callback responsibility, or controller admission. |
| 2 Sep 2026 | **Optimize remediation for parallel throughput and token efficiency.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Cohesive sessions continue across compatible slices without routine controller returns; focused checks run during development and expensive aggregates run once after bytes stabilize; valid reviews are reused; concrete findings and lease conflicts are consolidated; unrelated or environment-sensitive failures are attributed rather than allowed to create correction loops. Safety, required evidence, exact leases, and dependency serialization remain unchanged. | R02 must collect the complete failure set in one faithful aggregate rather than repeatedly stop at the first unrelated failure. The controller refills every released disjoint lane immediately but does not manufacture unsafe concurrency on the shared migration/generated-contract lane. |
| 2 Sep 2026 | **Apply a proportional verification budget to every remediation packet.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Before dispatch, the controller assigns the smallest sufficient tier: test/fixture corrections run the exact regression plus affected module; ordinary product changes run red/green plus focused service/API and adjacent compatibility; money, authentication, migration or concurrency changes add only the relevant real-PostgreSQL/race/migration evidence; generated-contract changes add synchronization checks. A whole-repository or whole-frontend aggregate is prohibited per slice unless the packet itself is an approved integration checkpoint. One stabilized focused aggregate per cohesive packet is the default; unchanged accepted reviews and evidence are reused. | Broad suites are reserved for R02, R59, package closure, or an explicitly justified cross-package integration checkpoint. Unrelated failures are attributed once and repacketed; they do not trigger repeated broad reruns. The controller must reject or tighten any future dispatch whose verification scope exceeds this budget without a concrete risk-based reason. AUT-006 already complies and is not interrupted. |
| 2 Sep 2026 | **Vehicle approval uses an administrator-entered end date that may exceed document expiry.** | Direct project-owner/developer clarification in the active remediation controller, 2 Sep 2026; recorded as D31 | The driver supplies vehicle documents; an authorised Cardvert admin reviews them and selects the approval end date. No automatic earliest-document-expiry rule or 12-month cap applies. The chosen date and actor remain auditable, and expiry requires a new reviewed approval. | ONB-004 becomes eligible for current-source reviewed execution rather than remaining parked. |
| 2 Sep 2026 | **Reject duplicate driver NIN, normalized phone, or payout bank account; freeze planning-source links at terminal campaign states.** | Direct project-owner/developer answers in the active remediation controller, 2 Sep 2026; recorded as D30 | Duplicate checks must use protected/normalized authority without identity disclosure. Planning-source links remain editable for draft, pending, approved, scheduled, active, and paused campaigns; completed, cancelled, and rejected campaigns are read-only history. | ONB-003 and AUD-006 become eligible for current-source reviewed execution; neither is silently treated as already implemented. |
| 2 Sep 2026 | **Advertiser logins are single-company; one Cardvert admin may complete all driver approval checks.** | Direct project-owner/developer clarification in the active remediation controller, 2 Sep 2026; recorded as D29 | Advertiser membership permits exactly one active advertiser organization per login; Cardvert admins are unaffected. No maker-checker separation is added across bank verification, person/payee approval and vehicle approval, but existing immutable actor evidence remains mandatory. | AUT-007 becomes eligible for bounded enforcement after the central migration lane clears. ONB-005 requires current-source confirmation only and no manufactured implementation if existing audit authority already satisfies D29. |
| 2 Sep 2026 | **Driver activation uses administrator authorisation plus a driver-completed one-time setup link.** | Direct project-owner/developer clarification in the active remediation controller, 2 Sep 2026; recorded as D28 | Applies to the linked invited driver after person/payee and vehicle approval. The administrator never assigns the password; completion is single-use, rotates session authority and invalidates prior onboarding access. No live delivery provider is implied. | ONB-009 leaves the parked client-decision list and becomes eligible for current-source reviewed execution. |
| 2 Sep 2026 | **Adopt the recommended developer-policy answers** — privilege elevation reauthenticates and revokes globally; ambiguous End stops capture and retries identically; registration abuse uses scoped non-revealing limits plus alerts; bundled or managed PostgreSQL/Redis are allowed with production TLS/auth/host/secrets; coverage policy waits until runtime defects are finished. | Direct project-owner/developer response in the active remediation controller, 2 Sep 2026; recorded as D27 | Supplies behavior but no threshold, provider, hostname, secret, deployment or external evidence. Each formerly ambiguous candidate still requires current-source confirmation and a bounded reviewed implementation packet before code changes. | AUT-006, OFF-008, ONB-008 and REL-007 are eligible for execution planning rather than client blocking. R17/TST-007 remains deliberately parked. |
| 2 Sep 2026 | **Use Sol/medium for new remediation sessions by default** — reserve Sol/high or xhigh for an explicitly identified, unusually critical boundary rather than applying it automatically by domain label. Also surface developer-answerable decisions directly instead of parking them as if only the client could answer. | Direct project-owner/developer instruction in the active remediation controller, 2 Sep 2026 | Every future dispatch records its model and actual highest-risk justification. Sol/medium is the default; Terra remains suitable for ordinary bounded implementation/review and Luna for read-only inventory. A higher Sol reasoning level requires a concrete critical risk that medium cannot responsibly cover. Already-running sessions are not restarted solely for this policy change. Client/legal/external items remain parked, while developer-resolvable questions are presented to the owner in small decision batches. | Changes future dispatch/model selection only. Current safely running packets retain their existing models. The controller must solicit and record developer answers before treating those rows as blocked or parked indefinitely. |
| 2 Sep 2026 | **Separate buildable defects from client/external follow-ups** — park work that cannot be completed from repository authority in `to-do.md`, and keep the active remediation queue focused on product and engineering defects that can be fixed locally. Logout must revoke sessions on every device. | Direct project-owner/developer instruction in the active remediation controller, 2 Sep 2026 | Client/business/legal choices, unanswered later developer policy, external systems/evidence and trigger-dependent observations remain explicit and incomplete in `to-do.md`. R11 uses existing global `session_version` authority; R06 may apply the reviewed historical-downgrade safety exception; R28 derives admin activation from D18/Q15; R36 uses the reviewed durable migration/model/signing design. R17 is parked as undetermined CI coverage policy. | Unblocks R11, R06, R28 and R36 planning/execution without inventing client or external facts. Parked items do not consume implementation capacity or block independent engineering slices; all source IDs remain reconciled for final reporting. |
| 2 Sep 2026 | **Prefer cohesive multi-slice implementation sessions over one-slice handoffs** — pre-authorize each visible owner to continue through as many sequential slices as form one truthful bounded packet, rather than returning after every slice. | Direct project-owner amendment in controller task `01a05de2-0b5d-73f0-ae3d-0e979b734658`, 2 Sep 2026 | A packet may combine only dependency-aligned slices with compatible code surfaces, model gate, verification environment, specialist reviews and rollback/partial-completion semantics. Every slice/candidate ID, internal red/green checkpoint and separate admission receipt remains mandatory. Central migrations, generated contracts, shared fixtures, controller documents and overlapping services remain serialized. Packet size is evidence-derived, never an arbitrary target such as five. Owners proactively callback only when the full packet completes, blocks, conflicts or needs steering. | The rolling scheduler now prefers longer cohesive lane packets: current S09 may continue R26→R27 after a verified internal R26 checkpoint; future control, privacy, campaign, reporting and release sessions receive the longest safe dependency-aligned chain available. Controller admission still reconciles every slice exactly once at the packet terminal boundary. |
| 2 Sep 2026 | **R02 branch authority: every direct branch push runs CI** — retain the accepted GOV-003/R02 and architecture contract rather than narrowing it to master-plus-PR. | Direct owner choice in the active remediation controller, 2 Sep 2026 | R02 may additionally edit only `tests/test_validate_progress.py` to remove the stale master-only assertion and require every-branch push. The preserved three-path implementation, accepted plan/graph reviews and all other behavior remain unchanged. | Clears the R02 owner block and resumes its existing visible task; R03/R17 remain dependency-held until R02 admission. |
| 2 Sep 2026 | **Resume the approved Cardvert remediation programme from the exact safe pause snapshot** — preserve accepted commits and safely frozen work, avoid duplicated slices/reviews, and return to dependency-safe rolling dispatch. | Direct project-owner instruction relayed from controller task `01a001ce-d025-7531-a84c-7498cd819eda`, 2 Sep 2026 | Reactivates only the unchanged frozen R02, R09 and R35 packets first. R09/R35 may proceed through admission on existing valid receipts; R02 may resume only against its preserved exact lease and evidence. Later work retains the admitted R01–R60 graph, disjoint shared-checkout leases, the existing risk-based model gates, all 29 non-executable dispositions, and all external/live prohibitions. | Lifts `PAUSED — OWNER-SCOPE-RECONCILIATION`, sets the controller `ACTIVE`, and restores work-conserving refill after current frozen packets are reconciled. |
| 2 Sep 2026 | **Pause the admitted remediation programme for owner scope reconciliation** — preserve accepted commits and freeze every unfinished packet while the owner reassesses which of the 86 FIX candidates remain current product problems rather than CI/test/evidence/docs work or disproportionate hardening. | Direct project-owner instruction relayed from controller task `01a001ce-d025-7531-a84c-7498cd819eda`, 2 Sep 2026 | Preserve all accepted slices through R34 product commit `a95a7ca`; preserve the exact uncommitted R02, R09, R35 and unrelated user/audit bytes without staging, reverting, resetting, admitting or discarding them. No new R-slice, correction loop, review loop, writer, or lease may start. An already-running non-destructive R02 review may finish only to produce its frozen receipt. | Sets the controller to `PAUSED — OWNER-SCOPE-RECONCILIATION`, current writer capacity to zero, and awaits a narrowed approved inventory before any scheduler action resumes. |
| 1 Sep 2026 | **Use Claude Opus 5 High for the next two implementation sessions after the current set clears** — create the next two safely ready, mutually disjoint packets as visible Claude desktop Code sessions. | Direct project-owner amendment in controller task `01a05de2-0b5d-73f0-ae3d-0e979b734658`, 1 Sep 2026 | The controller must still select packets from the admitted graph, preserve exact slice/candidate IDs, dependencies, leases, stop conditions, review gates and shared-checkout safety. Sessions use saved Mobility `master`, direct checkout, no worktrees, Opus 5 / High. No external action or authority boundary expands. | Deferred trigger: after the currently active/reviewing R13, R24 and R34 set reaches safe admission/steering points, allocate the next two compatible ready implementation packets to Claude; do not displace current owners. |
| 1 Sep 2026 | **Execute the admitted Cardvert audit-remediation programme** — deliver the 86 FIX candidates through the dependency-safe R01–R60 graph with rolling, maximally useful parallel dispatch. | Direct project-owner authorization in task `01a05de2-0b5d-73f0-ae3d-0e979b734658`, continuing source task `01a001ce-d025-7531-a84c-7498cd819eda`, 1 Sep 2026; visible-task/concurrency and event-driven-callback amendments in the same controller task | Owns PKG-10, the exact admitted slice/candidate graph and repository fixes. Two implementation writers remain the baseline; a higher current capacity is authorized only with a recorded, exact disjoint-work justification. Implementation runs in visible top-level Mobility tasks directly in the saved checkout without worktrees, reusing a task across its compatible multi-slice session; internal subagents are review-only. Every visible task messages this controller only when its owned slice or planning packet completes, blocks, conflicts or requires steering; the controller then reconciles actual state before review, admission or refill. Periodic polling and recurring monitoring automation are disabled. Central configuration, migrations, contracts, shared fixtures and this file serialize. The 9 DEFER, 12 OWNER DECISION and 8 EXTERNAL INPUT findings remain non-executable; COM-008 remains open. No deployment, live payment/provider action, credential invention, external publication, legal approval, or live-evidence claim is authorized. The UI/product-flow prompt suite remains paused. | Activates PKG-10 and R01 first. After R01 acceptance, use the deterministic session partition and refill every safely justified writer slot without artificial batch boundaries. |
| 1 Sep 2026 | **Preventive minimal-structure and diff-review refinement** — prefer existing repository, standard-library, native-platform or installed capabilities before adding structure, and strengthen the existing post-build review for duplicated capability, unnecessary dependencies, self-justifying structure and low-value changed tests. | Direct project-owner request, 1 Sep 2026 | Owns one universal contribution-ready rule and the existing `minimal-change-review` mandate. It creates no new skill, review stage or repository gate and does not change VFD, OFD or DCD. | None. The completed controller state and terminal PKG-09/W4-04B pointer remain unchanged. |
| 1 Sep 2026 | **Durable deferred-obligation policy** — future package/checkpoint instructions must survive chat, agent and session boundaries as concise trigger/action/evidence-pointer reminders in the existing authoritative record. | Direct project-owner request, 1 Sep 2026 | Owns global instruction policy plus Mobility's root `AGENTS.md` mapping to this document and this control row. It creates no new planning document and adds no product code, API, data-model, workflow, architecture or decision change. | None. The completed controller state and terminal PKG-09/W4-04B pointer remain unchanged. |
| 1 Sep 2026 | **Independent-audit corpus and remediation programme** — preserve the completed GPT-5.6 Pro, Claude Opus and Codex audit responses in-repository; inventory omissions; reconcile, deduplicate and evidence-check their findings; produce a dependency-safe remediation order before any fix work; and preserve the later UI/product-design prompt suite for a separate pass. | Direct project-owner request, 1 Sep 2026 | Owns `issues/**` and `.codex/delivery/cardvert-audit-reconciliation/**` for collection and planning. Raw audit responses remain provenance artifacts rather than product authority. Any later product-code correction requires a finding-specific reviewed contract, current-source verification and the normal contribution-ready gate. External/live inputs remain external; this request does not mark them present. | None. The completed build-controller state and terminal PKG-09/W4-04B pointer remain unchanged. |
| 1 Sep 2026 | **Final Cardvert/Terrax Media identity sweep** — remove every tracked reference to the superseded working name and use Cardvert for the product/app and Terrax Media for the business. | Direct project-owner request, 1 Sep 2026 | Owns repository branding copy, comments, tests, documentation, the auth timing-equalizer sentinel, the saved-theme key and the offline queue database name. The two local persistence names are intentional pre-distribution clean breaks: no legacy fallback is retained and IndexedDB schema/version behavior is unchanged. Git history, dependencies and external services are excluded. | None. The completed controller state and terminal evidence pointer remain unchanged. |
| 28 Aug 2026 | **Repository instruction normalization** — make root and nested `AGENTS.md` the only active repository instruction sources and remove the legacy lowercase `agent.md`. | Direct project-owner request, 28 Aug 2026 | Owns repository instruction wiring only: root `AGENTS.md`, `CLAUDE.md`, and removal of `agent.md`. Historical `docs/build-loop/**` evidence remains unchanged. Adds no product code, API, data-model, workflow, architecture, or decision change. | None. The completed controller state and terminal evidence pointer remain unchanged. |
| 25 Aug 2026 | **Terrax Media public landing page** at `/landing` — brand-grounded marketing page for the OOH vehicle-advertising product, built from `docs/brand/terrax-media/` and the D18 Q1–Q34 confirmed answers. | Direct project-owner request, 25 Aug 2026 | Owns only `frontend/src/app/landing/**` and `frontend/public/brand/terrax/**`. It does not alter API, data-model, business-logic or package authority. | None. The public marketing surface is outside the 71-item MVP checklist. |
| 25–26 Aug 2026 | **Visual directions 7–9** for the demo/pitch theme system. **7 “Terra Grain”** and **8 “Coverage”** are grounded in `docs/brand/terrax-media/`; **9 “Broadside”** is adapted from the owner-supplied Terrax landing page. | Direct project-owner request, 25–26 Aug 2026 | Owns the shared direction surface: `frontend/src/app/globals.css`, `frontend/src/lib/themes.ts`, `frontend/src/lib/fonts.ts`, `frontend/src/app/layout.tsx`, `frontend/src/lib/map/config.ts`, `frontend/public/themes/**`, theme tests and `docs/design/**`. Adds no API, data-model, business-logic or workflow change. | None. The switchable design directions are a demo/pitch affordance outside the 71-item MVP checklist. |

### Approved post-remediation correction register

**Correction authority:** aggregate contract V3, source-validated and independently
reviewed by Sol/high in this controller task; exact implementation approval on
6 Sep 2026. The owner then froze direct Astra implementation and two Sol/medium
implementation reviews. This register is the executable direct-owner exception;
historical audit files and chats create no additional scope.

**Entry state:** HEAD and local `origin/feat/post-remediation-audit-baseline` both
`00918531b2bb37a1d184d1d4f917f659b9e4d80b`; branch `master`; no tracked/staged
changes. Preserve the four files in the pre-existing untracked
`.codex/delivery/cardvert-audit-reconciliation/`, the four `cardvert-*-38094d6.zip`
archives and `tests/test_audit_route_coverage.py.orig`. All nine initial hashes
were rechecked unchanged before approval. Never reset or substitute the baseline.

**Implementation owner:** this existing Astra session, exclusively. Migrations,
generated contracts and shared files are serialized. No implementation subagents
or simultaneous Astra owners. Current correction work: **Local A+B implementation accepted; execution/external gates remain open**.

| Macro phase | Dependency-ordered packet TODOs | Acceptance/review trigger |
| --- | --- | --- |
| A — DONE (local acceptance; external gates retained) | P01 C09; P02 C36; P03 C10/C11/C13/C16/C18; P04 C01/C02/C03/C07/C08/C12/C14/C15/C17; P05 C04/C05; P09 C35/H07; P10 C34/C37 | Sole Sol/medium review PASS after bounded browser and coverage resolution, 8 Sep. C34 remains an external gate; the six standard-image cases subsequently passed under the bounded owner amendment below. This is not release/deployment acceptance. |
| B — DONE (local acceptance) | P06 C06/C19/C20/C21/C22/C23; P07 C24/C25/C26/C27/C28; P08 C29/C30/C31/C32/C33 | Corrected final Sol/medium review PASS received. Existing Astra implemented and verified P06, then P07, then P08 directly, without implementation agents or handoff. Integrated evidence and external/execution gates are retained below. |
| Integrated closure — LOCAL PASS / GATES OPEN | All C IDs and H07 reconciled; contracts, recovery-head validation and integrated evidence reviewed | The one reserved fresh Sol/medium reviewer returned corrected PASS/no findings over both phases, full diff, red/green, deterministic/browser/local-stack evidence and exact external gates. No third implementation review dispatch; release/deployment closure remains blocked by those gates. |

P02 establishes controlled refresh tooling first; actual coverage baselines move
only against stabilized measured evidence without weakening D32. Every public
shape change synchronizes `openapi.json`, `docs/api/openapi.snapshot.json` and
`frontend/src/lib/api/schema.d.ts` immediately and reruns R14-B fixtures. New
schema changes are additive after 0084 in one linear chain; only the specifically
approved 0077/0082 downgrade guards may amend historical migration code.

**Accepted decisions and limits:** C15 retains minimal disclosure protection
indefinitely and removes TTL deletion because no governed source-retirement
authority exists; live legal approval stays closed. C17 preserves open/completed
history, hides blocked open tasks from actionable work and rejects completion.
C22/C23 use signed economic ledger facts and terminal-period membership for new
versioned runs, following `docs/measurement-methodology.json`; historical
calculations/manifests/issued reports remain immutable. C31 recovers only failed
or remaining creative work on the existing campaign under existing edit limits.
C34's incapable historical predecessor remains ineligible: implement the signed
capability and negatives, but no usable rollback or positive accepted-image
rehearsal claim until a genuinely compatible accepted predecessor exists.

**Admission rule:** each material behavioral test needs observed baseline red or
the smallest safe isolated mutation, then green. After each packet run focused
deterministic tests, inspect scope, record evidence/risks and update each owned
ID independently. Use real PostgreSQL for lock/race/serialization/migration and
money authority; local MinIO/S3 faults for promotion/deletion/delayed writes and
versions; real browsers for hostile same-site origins, End/visibility/IndexedDB,
partial acknowledgements and ordinary user journeys. Do not claim skipped jobs,
compiled code or a focused green check as aggregate proof. Preserve immutable
review/audit/financial/report history, D27 security, accepted payout terms,
screen-on PWA behavior and local evidence. No CASCADE, wildcard origins/CSP,
untracked provider attempts, blanket database-ahead readiness or weaker tests.

| Canonical ID | Disposition | Required behavior / evidence target |
| --- | --- | --- |
| C01 | VALID / IMPLEMENTED | Both KYC submission shells survive immutable decisions; one-way complete payload purge and reference fence commit before provider deletion. Preserve shared files; test restrictive FKs, concurrent binding and every crash boundary. |
| C02 | VALID / IMPLEMENTED | Exact orphan evidence reconstructs trustworthy bounds; current horizon rechecked before DDL; ambiguous recovery blocks destruction. |
| C03 | VALID / IMPLEMENTED | Confirmation adopts only exact matching promoted destination after rollback/lost response; source not deleted before durable authority. Local PostgreSQL/MinIO fault evidence below; live-provider gates remain. |
| C04 | VALID / IMPLEMENTED | Every issued write including transport retries must resolve; every version/delete marker adjudicated before CLEANED. Unknown outcomes stay nonterminal and visible. |
| C05 | VALID / IMPLEMENTED | Fresh User → Organization → Campaign → Membership locks precede ReportIssuance → PublicationIntent; real PostgreSQL request/completion inversion regression. |
| C06 | VALID / IMPLEMENTED | Due ordering includes durable worker-failure audit time, so a full failed prefix rotates without changing intent state or fabricating provider attempts. PostgreSQL/SQLite red-green plus preserved claim/finality races pass; evidence below. |
| C07 | VALID / IMPLEMENTED | 0077/0082 downgrade population checks and DDL serialize writers; populated deletion authority and unsafe publication states fail closed. |
| C08 | VALID / IMPLEMENTED | Calendar subtraction clamps short months while preserving UTC time; all retention surfaces share the correct cutoff. |
| C09 | VALID / IMPLEMENTED | Only the R59 contract test's import ordering changes; focused Ruff red/green, no skipped-CI implication. |
| C10 | VALID / IMPLEMENTED | Administrator creation requires D27 active actor/current-password/session proof and fail-closed limiter. |
| C11 | VALID / IMPLEMENTED | Invited admins cannot exercise admin authority/self-activate; all effective admin grants get reauthentication and correct global target revocation. |
| C12 | VALID / IMPLEMENTED | Collection authority before protected intent and again before confirmation/exact retry and protected vehicle evidence binding. Protected driver/applicant routes and binding regressions pass. |
| C13 | VALID / IMPLEMENTED | Locked report authorization refreshes stale ORM user/org/campaign/membership state; PostgreSQL revocation race. |
| C14 | VALID / IMPLEMENTED | Append-only typed actor/subject resolutions survive target/user deletion without users FK; distinct event counts and exact assignment/proof ownership exclude unrelated subjects. Migration 0086 preserves audit bytes and explicitly records unresolved targets/unrecorded actors. |
| C15 | VALID / IMPLEMENTED | Minimal disclosure history survives old TTL and delayed differencing; migration 0085 backfills absent expiry, blocks lossy downgrade; no invented retirement authority or live approval. |
| C16 | VALID / IMPLEMENTED | Shared unsafe BFF Origin/Fetch Metadata/media boundary before parsing/relay; full route inventory plus hostile same-site browser proof. |
| C17 | VALID / IMPLEMENTED | Purpose-matched active consent/current contact checked at creation, exact retry, actionable listing and completion; PostgreSQL withdrawal races preserve history and OPEN/COMPLETED states. |
| C18 | VALID / IMPLEMENTED | Exact configured storage origin in production CSP; real approved/hostile upload-origin checks; no wildcards. |
| C19 | VALID / IMPLEMENTED | New group members, signature changes and insufficient evidence retain existing unresolved replay flags and their money holds. Only governed review resolves them; 78 fraud/replay/earnings checks pass. |
| C20 | VALID / IMPLEMENTED | Earlier ended/unsealed payable predecessors block later cap allocation until chronological processing; shared-day and midnight conservation. |
| C21 | VALID / IMPLEMENTED | Frozen accepted start and end both govern admission despite mutable campaign edits. |
| C22 | VALID / IMPLEMENTED | New versioned reports freeze nonvoided signed ledger economics and coherent cutoff; no debt/settlement double count or missing-ledger fallback. |
| C23 | VALID / IMPLEMENTED | New denominator uses ended_at in the half-open period; active-at-boundary separately disclosed; no missing/double-counted cross-period trips. |
| C24 | VALID / IMPLEMENTED | Durable identical End request; current-trip flush precedes reconciliation across same-page/reload lost responses. |
| C25 | VALID / IMPLEMENTED | One End generation fences every asynchronous watcher/resume/write/manifest/flush/release boundary; no capture after End is sent. |
| C26 | VALID / IMPLEMENTED | Cancellation remains a distinct terminal historical capture cutoff, including quarantine adjudication. |
| C27 | VALID / IMPLEMENTED | Heading [0,360), optional invalid sensor readings normalized before immutable queue/hash; valid peers and old retained evidence preserved. |
| C28 | VALID / IMPLEMENTED | Atomic encrypted signed receipt/dispositions; accepted/rejected/settled counts truthful across reload; no settled-batch resend. |
| C29 | VALID / IMPLEMENTED | Upload cache binds exact selected file/purpose/access context; replacement and stale async completion cannot reuse wrong IDs. |
| C30 | VALID / IMPLEMENTED | Application convergence from both approval orders and exact retries with one audit/decision outcome; D28 activation stays separate. |
| C31 | VALID / IMPLEMENTED | Recover failed creative attachment on already-created campaign across retry/reload without duplicates or edit-authority bypass. |
| C32 | VALID / IMPLEMENTED | Ordinary idempotent demo seed establishes real production Start authority; normal persona completes the trip flow without R59-only repairs. |
| C33 | VALID / IMPLEMENTED | Per-item unexpected email failures isolated, observable and durably recoverable with fair traversal. Expired uncertain claims recover above handled attempt cap using stable provider key. |
| C34 | EXTERNAL VERIFICATION REQUIRED | Local signed qualification/accepted-recovery capability and negative tests implemented; ordinary exact-schema/worker readiness preserved. Accepted capable predecessor and positive distinct-image forward-schema rehearsal unavailable. |
| C35 | VALID / IMPLEMENTED | Runtime 422 envelope, OpenAPI/snapshot/TypeScript agree; rejected inputs stay private; R14-B fixtures rerun. |
| C36 | VALID / IMPLEMENTED | Controlled trusted-ancestor inventory/policy refresh supports add/rename/delete without reducing D32 floors or accepting missing evidence. |
| C37 | VALID / IMPLEMENTED | Both image heads and signed predecessor identity derived/validated; final DB head exact; stale/multiple heads rejected. |
| H07 | Documentation correction implemented | Architecture §6.5 authentication limiter wording becomes fail-closed; runtime unchanged. |

**Audit accounting:** 37 canonical corrections + six duplicate entries + H07 =
44. Security X-01 maps to C18/H02; Security X-02, Money PA-X01, Workflow F11 and
Horizontal H01 map to C09; Money PA-M06 maps to C04. No duplicate implementation.

**Evidence at admission:** exact refs/worktree and nine untracked hashes PASS;
`scripts/validate_progress.py` PASS; tracked/staged diff checks PASS; focused
`ruff check --no-cache tests/test_r59_real_stack_contract.py` FAIL, one I001.
Both OpenAPI artifacts advertise 239 HTTPValidationError validation responses.
No behavioral suite, migration, browser, provider or recovery rehearsal ran in
planning. V3 independent review PASS resolved six findings: both KYC payloads,
all storage attempts/versions, durable actor/subject links, no invented disclosure
retirement, incapable predecessor gate, and both authoritative image heads.

**Packet evidence (uncommitted working tree, not exact-SHA CI):**

- P01/C09: baseline Ruff I001 observed; the single blank-line correction passes
  focused Ruff and all seven `tests/test_r59_real_stack_contract.py` tests.
- P02/C36: 28 coverage-policy tests plus the seven R59 contract tests pass
  (35 total). Twelve initial refresh tests failed against the missing baseline
  capability; the CI-wiring regression also failed against the bootstrap-only
  workflow. Deliberately disabling ratio/inventory/receipt/instrumentation guards
  produced 11 expected failures; disabling ancestry/eligibility guards produced
  two expected failures. Both temporary mutations were restored before the
  final 35-pass run. Tests use isolated temporary Git repositories; no Mobility
  commit was created. Actual `coverage/baseline.json` is unchanged and its final
  refresh remains an integrated evidence obligation. No remote CI run is claimed.
- P03 in progress: ten new administrator API cases failed before the grant
  correction; all 25 administrator tests now pass. Five real-PostgreSQL stale
  report-scope cases failed before fresh locked reads and pass afterward.
  Administrator frontend tests demonstrated four failures before the password
  flow and now pass five cases. The shared BFF boundary demonstrated 15 denial
  failures before correction; all 21 boundary/proxy cases now pass. All three
  public contract artifacts are synchronized; 115 preserved PWA/session/queue/
  tracker fixtures pass and TypeScript passes. The combined authentication-race
  and report run returned 62 passes, five report failures, no skips. Those five
  reach the renderer with SQLite's timezone-less issuance timestamp; an
  in-memory baseline authorization substitution reproduced the same failure.
  P05 must resolve the test-environment mismatch and demonstrate publication on
  real PostgreSQL before accepting its integrated evidence. No renderer checks
  or immutable report timestamps may be weakened to bypass this failure.

- P03 accepted for local packet progression: four additional PostgreSQL
  creation/activation versus actor-revocation interleavings pass; bypassing the
  session-version comparison in memory made both containment-first cases fail,
  and the restored run passes all four. Eight live Caddy/browser checks pass;
  the three positive exact-origin cases failed under the baseline CSP, and the
  browser upload test also failed under an in-memory baseline Caddy substitution.
  The configured origin receives one synthetic multipart upload; the other
  origin receives none. A running Next/Chromium same-host, different-port
  hostile-origin POST returns 403 with zero backend calls; the same-origin
  bodyless POST returns 200 with exactly one backend call. This exposed Next's
  empty body stream, now covered by byte-based empty/nonempty stream tests.
  All 28 focused frontend tests, TypeScript, scoped ESLint/Ruff, contract
  regeneration check, progress validation and diff whitespace checks pass.
  OpenAPI/deployed-boundary/release-preparation tests pass 462 cases. P03 diff
  reviewed for scope. Provider MinIO/IAM/versioning/CORS verification remains
  part of integrated storage evidence; no live-provider or deployment claim.

- P04/C08: five short-month/timezone cases failed before correction; all seven
  calendar-cutoff cases now pass. C02: five migrated PostgreSQL orphan-recovery
  tests failed before correction; the 26-case lifecycle suite passes, followed
  by 12 affected detach/recovery cases after moving the global refusal gate
  ahead of all destruction. Recovered receipts retain exact reconstructed
  bounds; incomplete/conflicting/unclaimed/currently retained orphans stop the
  run, and current settings are rechecked at the drop boundary. C07: all three
  populated 0077 states and both check-to-DDL writer races failed before guards;
  all 13 guard/0077/0082 migration tests now pass, including empty down/up and
  schema drift checks. NOWAIT locks include authority, FK parents and fenced
  reference tables so busy cross-table writers make downgrade fail closed.
  Focused Ruff passes; these are isolated local databases, not live retention.

- P04/C03/C12: the upload/KYC/person-payee/vehicle/installation suite passes
  68 tests. Baseline failures cover four protected intent cases, four protected
  confirmation cases, two vehicle binding cases, two S3 source-preservation
  cases and two PostgreSQL confirmation rollbacks. Removing the collection gate
  in memory makes both applicant confirmation/retry tests return 201 instead of
  the required privacy denial; restored tests pass. Two actual local MinIO
  copy-response-loss/database-rollback recoveries pass, including source expiry
  simulation. Disabling destination adoption in memory makes both fail and
  three adopted-object metadata tests return the wrong disposition; restored
  tests pass. Temporary objects remain under the existing unconfirmed lifecycle;
  no production lifecycle/IAM/provider authority is asserted.
  A broader driver-approval run exposed two frozen-binding fixture failures
  before the intended eligibility assertions. Baseline-source reproduction and
  fixture correction remain integrated-verification obligations; do not weaken
  production trip admission. The initial applicant test configuration omitted
  registration enablement; it was corrected before recording useful red/green.

- P04/C15: all three delayed-query/scheduled-retention cases failed on the old
  TTL behavior. All 32 disclosure/composition/0045/0085 checks pass with real
  PostgreSQL enabled and no skips. Omitting 0085's expiry backfill in memory
  fails the migration preservation assertion; restored migration passes. The
  migration retains every other history field and refuses populated downgrade.
  Live legal approval remains absent; no source-retirement authority is invented.
- P04/C17: ten of twelve withdrawn, purpose-mismatched and superseded-phone
  cases failed against baseline. The 22-case contacts/notifications suite now
  passes, including both PostgreSQL completion/withdrawal orders. Restoring the
  baseline contact functions in memory demonstrates premature completion while
  withdrawal holds authority; the corrected path waits and then denies. Tasks
  remain OPEN when blocked, completed evidence stays visible/replayable, and
  neither consent nor task history is deleted. Focused Ruff passes.
  Both broader driver-approval fixture failures were reproduced with all `app`
  Python modules loaded from exact baseline Git blobs in memory; they remain
  local integrated-verification obligations rather than corrected behavior.

- P04/C14: target-aware DSR count was zero on baseline instead of the two
  subject-targeted case events. Corrected inventory counts actor/target overlap
  once and excludes foreign-subject events. The 86-case audit/migration/DSR/
  contacts/payee aggregate passes with real PostgreSQL enabled and no skips;
  the separate owned 0085/0086 schema comparison also passes. Atomic attribution
  survives profile/actor deletion and rolls back with its event. Compound
  measurement/report links use proof-bound subjects; campaign events use only
  the exact matching assignment. Payee, bank account, batch/line/intent and
  correction-trip ownership are exercised without provider execution.
  Restoring actor-only resolution in memory fails all 34 missing-target cases
  plus atomic attribution; separate corrected-fixture runs fail compound
  proof, money and frozen-migration attribution assertions. Removing backfill
  source locks lets concurrent profile deletion cross the migration boundary;
  restored migration serializes it and retains attribution. The migration
  leaves audit bytes unchanged, refuses populated downgrade, and rejects
  resolution update/delete/truncate. It never guesses unresolved historical
  identities. These gaps remain explicit operator/legal evidence obligations.
  The new subject-aware self-audit count exposed assessment-retry drift; exact
  system-count retries now preserve accepted counts while current absence/
  erasure checks remain. A changed external-count test caught over-broad retry
  handling (201); the narrowed system-only handling returns the required 409.
  Public response schemas are unchanged; no new privacy response wording or
  live DSR approval is claimed. Next P04 work is C01's durable KYC purge shells.

**Deferred closure obligations:** after A review PASS assess session health before
B; after all bytes stabilize complete the one fresh final review and reconcile
all IDs. Actual provider IAM/CORS/versioning, legal/privacy/report methodology,
physical-device GPS/battery, accepted recovery images, staging/production and
pilot evidence remain open when unavailable. Exact-new-SHA CI requires separately
authorized commit/external CI: never attribute uncommitted corrections to HEAD.
Final report must identify SHA/worktree, individual dispositions/H07, actual
red/green and integrated evidence, reviews, risks, and distinct behavioral-clean,
release-ready and deployment-ready verdicts. No completion by association.

- **P04 / C01 — locally demonstrated:** migration 0087 retains both submission
  identities and restrictive immutable-review links. Complete NIN/vehicle-payload
  clearing, document detachment, audit authorization and object-deletion receipts
  commit before provider calls. One-way database guards reject partial/unaudited
  retirement, restoration, identity changes and new document bindings. ORM and SQL
  writers take the parent before the file; legacy unretired deletion owners stay
  blocked while current-policy retirement supplies authority. Shared files survive;
  payload consumers return 410 and sanitized reads expose null payloads/purge time.
  Five migrated tests cover both decision chains, failed commit, reveal/rewrap,
  document-binding serialization, empty/live-payload upgrade/downgrade, populated
  refusal and writer locking; focused retention/KYC/person-payee/OpenAPI aggregate
  **41 passed**, including the nine updated lifecycle invariants. The baseline
  driver/vehicle boundary tests were red before implementation. In-memory removal
  of the 0087 guards makes both unauthorized-clear cases fail, and removing ORM
  parent-first locking makes the real race fail on the held file row; restored
  tests pass. Actual local MinIO delete-then-lost-reply recovery passes: all three
  receipts complete, the retired payload stays absent, and three peer objects
  survive. Restoring both baseline deletion entry points in memory makes this
  MinIO test fail because the payload was not durably retired; restored test passes.
  All three generated contracts are synchronized; 115 preserved queue/session/PWA/
  tracker fixtures, TypeScript and scoped Ruff pass. Architecture §19.4 and the
  incident runbook now describe durable cleanup rather than rollback resurrection.
  Inspected the C01 diff; no review/financial/audit history is cascaded away. Live
  retention authorization and production storage/versioning/IAM/CORS remain open
  external gates. The two pre-existing frozen-binding fixture failures remain an
  integrated obligation. P04 is locally demonstrated; next is P05 C04/C05.

- **P05 / C04, C05 — locally demonstrated:** request and publication completion
  use User → Organization → Campaign → Membership → Issuance → Intent order;
  immutable measurement runs no longer take an overlapping row lock. The real
  PostgreSQL scope-versus-publication test fails before the change because the
  publisher owns the issuance while waiting for scope, and passes afterward.
  Migration 0088 adds per-call registered/settled/uncertain write receipts and a
  required default-free generation protocol marker. Registration and retirement
  serialize on the intent; cleanup skips unresolved calls before its batch limit;
  both settled calls are required for publication. The S3 generated-write client
  issues exactly one SDK request and distinguishes uncertain transport failure.
  Cleanup deletes/verifies every exact-key version and marker, preserving peers.
  Existing non-complete generation history, including old cleaned claims, stays
  unchanged apart from an explicit legacy protocol classification and linked
  unknown-write evidence. Old publishers cannot create new untracked generations.
  No timeout, empty read or later successful generation establishes settlement.
  Unresolved legacy/provider calls require external evidence and a separately
  reviewed reconciliation procedure; no receipt rewrite or invented proof exists.
  CSV/PDF delayed-call tests were red (cleanup returned 1 prematurely), then pass.
  Falsely settling uncertainty makes both the service and real-MinIO late-write
  tests fail; omitting migration backfill fails all five affected legacy states;
  disabling receipt guards or adding an unsafe marker default fails their tests.
  Restoring SDK retries makes a local HTTP fault server observe five PUTs instead
  of one; restoring ordinary delete leaves versioned MinIO bytes/markers behind.
  All mutations were process-local; the owned fault-test bucket was cleaned.
  Final report/storage/OpenAPI/inventory aggregate **82 passed**, including nine
  real-MinIO cases; final 0088/0082/0077 downgrade/serialization aggregate **17
  passed**. Earlier report/renderer/migration/inventory aggregate passed 61.
  The five inherited SQLite report failures are resolved without weakening the
  renderer: UTC database timestamps are serialized with their zone when freezing
  new snapshots/render metadata. Two previously unreachable PDF test assertions
  now decode the embedded Unicode map and retain every disclosure/hash assertion
  across layout wrapping. Published/frozen historical bytes are not rewritten.
  Scoped Ruff and diff whitespace checks pass; inspected P05 source/migration/test
  diff. Architecture §27 and the operations runbook describe settlement, lock
  order and unknown/legacy gates. P09 C35/H07 is next; Macro A review remains
  reserved until all A packets and integrated verification stabilize.

- **P09 / C35, H07 — locally demonstrated:** FastAPI's shared 422 response now
  uses the project's `ErrorResponse`/`ErrorDetail` schema. Existing exception
  handlers, codes, messages, details and input redaction are unchanged. Both new
  contract tests failed against the prior HTTPValidationError contract and now
  pass, including actual path/query/body validation and request-ID preservation.
  OpenAPI, snapshot and generated TypeScript are synchronized; backend error/
  OpenAPI suite **25 passed**, all 115 preserved queue/session/PWA/tracker fixtures
  pass, TypeScript passes, and scoped Ruff plus byte-stability checks pass. One
  initial command named a nonexistent contract-test file and collected no tests;
  the corrected command produced the reported 25-pass result. Architecture §9
  documents the common envelope. H07 changes only §6.5's obsolete limiter wording
  to D27/R12 fail-closed behavior; queue-loss recovery remains unchanged. Inspected
  the contract/documentation diff. P10 C34/C37 is next; accepted distinct-image
  recovery evidence remains explicitly external, never supplied by a modified
  copy of the historical previous image.

**P10 local evidence (C34/C37):** 521 readiness/release/authority tests pass,
including real PostgreSQL exact-forward/multiple-row rejection, public-readiness
isolation with a signed token present, and actual isolated Compose/container
preservation of signed values containing dollar characters. Baseline unsigned
`--allow-database-ahead` accepted authority (red); it is now rejected. In-memory
signature bypass produces five red cases; bypassing recovery worker checks one;
restoring the baseline incomplete qualification validator six; removing the
recovery health override one; skipping exact image-label validation one; using
the baseline rehearsal's obsolete head one. All restored checks pass. The real
historical-predecessor script negative exits before any build/infrastructure
command; no application or packaging code is copied into the predecessor.
Version 3 receipts and separate qualification/recovery scopes replace the broken
public-readiness recovery assumption. Full Ruff, shell syntax, progress validator
and whitespace checks pass. Source/configuration/doc diff inspected. C34 remains
`EXTERNAL VERIFICATION REQUIRED`: no accepted capable predecessor, signed positive
two-image rehearsal or deployment evidence is claimed. Next: finish aggregate
Macro-A verification and inspect its complete diff before the sole Macro-A review.


**Macro-A integration in progress, 7 Sep 2026:**

- KYC retirement now uses the shared exact-key all-version deletion capability.
  Actual versioned MinIO reproduced the old error: completed deletion receipts
  while prior object versions survived. Versioned and unversioned loss-of-reply
  recovery plus KYC suites pass **24 cases**. A separate provider-remains test
  verifies durable pending authority, retry count and error evidence; replacing
  version deletion with ordinary deletion in memory makes it fail, and the
  restored test passes. Peer objects and immutable review shells survive.
- Seven existing trip fixtures lacked accepted payout bindings. The baseline
  application reproduces the early admission failure; explicit fixture bindings
  restore the original intended assertions, without changing trip authority.
  The complete affected vehicle/exclusivity/financial-authority files pass
  **41 tests**. Historical migration tests are being reconciled separately;
  no production downgrade guard is relaxed.
- All **518 frontend tests in 94 files** pass with coverage, followed by passing
  TypeScript, ESLint and production build. Pinned Node 26 exposes native global
  Web Storage inside Vitest workers; `execArgv` disables that experimental global
  so the configured jsdom storage works. The unchanged six report-panel tests
  failed before this runner correction. No test assertions or package scripts
  were weakened; this configuration change belongs in the controlled C36 receipt.
- Historical migration rechecks pass **13 cases**: target 0030/0031/0069
  backfill/downgrade assertions now run at their named revision, while empty
  full-head cycles and head schema checks remain. The three money fixture
  failures also reproduce on the baseline 0084 chain. Catalog drift mutations
  use a leaf primary key now that audit events have a restrictive subject FK;
  all eight mutation/restore assertions remain. Exact head/inventory obligations
  include all four approved migrations. Evidence: migration baseline/recheck/
  green logs under `/tmp/mobility-macro-a-*`.
- The administrator creation UI additionally demonstrates masked required proof,
  exact form submission, clearing after a rejected submission, and removing the
  proof field when selecting an ordinary role. Removing the proof field causes
  an observed regression failure; the restored UI test and TypeScript pass.
- All nine pre-existing untracked hashes were rechecked unchanged on 7 Sep;
  all 37 canonical rows occur exactly once, both refs remain at the required
  baseline, and the index remains empty.
- Current architecture inventory is **122 tables / 88 linear migrations** ending
  at 0088. P10's additional CLI/component/authority cases pass **60 tests**;
  the preceding readiness/architecture complement passed 70. Cached predecessor
  image labels resolve to actual heads 0082 and 0071, not current 0088; neither is
  accepted as a capable previous-image recovery rehearsal.
- Sole controller owns synthetic local services `mobility-correction-postgres`
  (60268), `mobility-correction-minio` (64252), and isolated Redis/ClamAV through
  `mobility-correction-relay` (58126/58125). Redis/ClamAV use the internal
  `mobility-correction-services` network; ClamAV updates are disabled and cached
  images/signatures are used. The two scanner integration tests accept an
  explicit local port, retaining default 3310. At programme closure remove only
  these task-owned services/network; never touch unrelated services. Evidence:
  `/tmp/mobility-correction-test-env.sh`, `/tmp/mobility-macro-a-*.log`.
- The 333-case backend focus run measured current product code: 332 pass,
  one already-collected publication warning assertion fails because in-process
  Alembic disabled its logger. The corrected test passes when deliberately
  starting with that logger disabled. No cleanup assertion changed. Full
  frontend coverage now passes **519 tests / 95 files**; changed frontend
  coverage is 92.7273% line / 87.3016% branch.
- Stable full verification is divided into two disjoint test-file sets:
  `test_migration*.py` uses its isolated disposable databases; all other files
  retain the complete PostgreSQL/Redis/MinIO/ClamAV integration configuration.
  Both run under coverage against the same unchanged product files, then their
  data is combined by coverage.py. This changes neither collection obligations
  nor instrumentation and creates no additional implementation owner. Evidence
  inventories/logs are `/tmp/mobility-macro-a-migration-files.txt` and
  `/tmp/mobility-macro-a-verified-*.log`. The earlier exploratory run remains a
  failure inventory, not final coverage authority.
- The exploratory full run finished **2,686 passed / 24 failed / zero skips**
  in 53 minutes. Its application modules and tests were collected before several
  recorded fixture corrections; its coverage is not final authority. The final
  failure inventory also exposed two incomplete trip-payout fixtures, a stale
  pilot test-node reference, a missing synthetic report input hash, the owned
  browser server's build lock, and a crash test's obsolete cleanup expectation.
- The two trip tests and three load-harness failures reproduce against baseline
  application source. Trip tests now use full financial authority and explicitly
  frozen classifier settings, with PostgreSQL for payout processing; old
  authorization bypasses and duplicate rule creation are removed. All **10 trip
  seal tests pass**, retaining quarantine/tamper, audit, day and recomputation
  assertions. The synthetic report fixture gains its actual canonical input
  hash and a recalculated fixture seal; the renderer, cohort and amounts are
  unchanged. A new input-hash assertion failed before correction. Pilot
  preparation references the existing renamed paid/failed-finality test, keeping
  node-existence validation. Load/preparation checks pass in the 27-pass focused
  complement; no live evidence or historical report is changed.
- The process-kill report test now demonstrates the C04-required outcome: one
  registered unsettled object survives, later generation reaches READY with two
  settled receipts, and no object key is duplicated. An in-memory child-worker
  mutation settling before the call fails the new receipt assertion; restored
  crash and commit-replay checks pass. The persistent synthetic provider now
  supplies verified single-version deletion for the shared storage contract.
- The task-owned Next server on 34217 was identified and stopped through its
  original tool session, releasing its build lock. The complete W403B correlated
  synthetic browser journey then passes; unrelated frontend service 3100 was
  untouched. Evidence: `/tmp/mobility-macro-a-w403b-browser.log`.
- All **195 migration tests pass** under fresh coverage in 11 minutes. The
  complete inventory is **231 files = 78 migration + 153 other**, disjoint with
  no omissions. The other-file run is active against stable product bytes with
  every local integration required. Fresh data files are
  `/tmp/mobility-A-verified-migrations.data` and
  `/tmp/mobility-A-verified-other.data`; combine only these completed green runs.
- The query-plan failure showed PostgreSQL selecting the equally selective
  entity index instead of the expected action index. Adding repeated historical
  actions on the same two entities makes the intended selectivity distinct; all
  exact index and result assertions remain. Five consecutive PostgreSQL runs
  pass after the observed failure. Evidence: query-plan-repeat-26 (red) and
  query-plan-stable (green) logs. Stable non-migration verification, combined
  coverage/provenance and the Macro-A independent review remain pending.


**Verification recovery, 8 Sep 2026:** On resumption, both required refs still
match 00918531 and the index is empty; the correction diff remains present.
The prior `/tmp/mobility-*` evidence and service leases are unavailable. The
interrupted non-migration run has no verifiable completion outcome and is not
accepted. Prior observed red/green results remain recorded above, but their
missing raw temporary logs cannot be supplied to the reviewer. Fresh full
verification is rerunning both disjoint shards, with durable logs, exit codes,
source hashes and coverage under ignored `coverage/correction-sep8/`; never
substitute the older `coverage/.coverage` or stale backend LCOV. Frontend coverage
is being renewed there as well. No product change is required by this restart.
The sole controller owns new `mobility-correction-sep8-{postgres,minio,redis,
clamav,relay}` containers and the internal `mobility-correction-sep8` network.
Ports are PostgreSQL 60329, MinIO 60332, Redis 60341 and scanner 60340; synthetic
configuration is `coverage/correction-sep8/test-env.sh`. Cached images only;
scanner updates disabled. PostgreSQL, Redis and scanner readiness passed, and
the owned private bucket was created. The differently configured, stopped
`mobility-correction-postgres` container and unrelated running services were
left untouched. At closure clean only the new owned leases, retaining evidence.
Fresh frontend verification passes 519 tests/95 files, TypeScript, ESLint and
production build. All nine pre-existing untracked hashes still match. The final
runbook inspection corrected C02's obsolete orphan log name and manual recovery
wording: reconstructed bounds and current retention authority govern DROP;
manual FINALIZE alone cannot authorize destruction. Runtime source is unchanged.
Preserved W401C browser checks pass separately without skipped cases: Pixel 7
Start/End with durable synthetic evidence, and iPhone-sized degraded authority
preventing Start. These are browser simulations, not physical-device proof.
Source/test hashes still match the verification-entry fingerprint.
The fresh migration shard passes **195 tests / zero skips** in 674 seconds,
with one existing TestClient deprecation warning. Its exit-code file is zero and
coverage is durable at `coverage/correction-sep8/migrations.data`. The other
shard contains 2,526 tests; together they match all 2,721 collected cases.
The non-migration shard finishes **2,525 passed / one failed / zero skips** in
2,359.91 seconds. The one failure is W403B browser Start blocked by a live
capability check. The unchanged correlated journey then passes once under
coverage and three more times individually. Its aggregate-only cause remains
unresolved and is explicitly submitted as a review risk, not hidden by a claim
that the aggregate itself passed. No capability check or test assertion changed.
Fresh coverage combines the migration shard, full other shard and focused
browser recheck; every one of the 2,721 collected tests has an observed pass.
The controlled C36 refresh passes: changed **94.2804% line / 88.6076% branch**,
global **87.1623% / 64.0758%**, backend **91.5705% / 77.2131%**, frontend
**62.9941% / 47.3424%**. Trusted floors and instrumentation remain unchanged.
The refreshed receipt and separate provenance verification pass. Post-browser
product/test fingerprints match; Ruff and diff checks pass. Evidence is in
`coverage/correction-sep8/{other,browser-recheck,browser-repeat-*,coverage-refresh,
coverage-provenance}.log`, with fresh coverage data alongside.
The sole Macro-A reviewer is **GPT-5.6 Sol / medium**, explicitly selected by the
owner for this multidisciplinary review; the owner amendment supersedes the
usual high-reasoning preference. Its ownership is read-only assessment of the
complete Macro-A diff, contract and evidence; it may not edit or spawn agents.
The review also covers the unavailable prior raw red/green logs and unresolved
aggregate-only browser failure. Macro B remains unstarted until review findings
are resolved and affected verification passes.


**Macro-A independent review — Sol/medium, 8 Sep: FIX (one P1).** The sole
reviewer checked all 120 entry hashes, all Macro-A IDs, the integrated security,
privacy, storage, migration, concurrency, publication, contract and recovery
boundaries. No material product defect, unsafe shortcut, unjustified file or
Macro-B implementation was found. The one P1 is the non-green aggregate browser
journey: four isolated passes do not explain the missing live capability. The
reviewer requires exact failure assessment/trace and a faithful rerun of only
the non-migration shard. Lost earlier raw red/green transcripts remain a disclosed
provenance limitation; the reviewer did not require recreating every mutation.
C34 and the existing external gates remain open.

The controller's bounded review fix adds a privacy-safe browser-console
assessment exactly when Start refuses, before its normal lock cleanup changes
the diagnostic state. It includes capability codes/results/actions, never
identity, GPS, tokens or credentials. This is verification observability only;
no Macro-B behavior or tracking decision is implemented. The W403B test retains
its exact active-health assertion, attaches the assessment on failure, rethrows
the failure and retains a browser trace. A new regression first failed because
no warning existed, then all **43 tracker tests pass**. A temporary test-only
missing-service-worker mutation fails that same browser assertion and captures
`SERVICE_WORKER_NOT_REGISTERED` plus the trace; the fixture was restored before
verification. TypeScript and changed-file formatting pass. Evidence:
`coverage/correction-sep8/start-diagnostic-{red,green,browser-mutation}.log` and
`start-diagnostic-mutation-trace.zip`.

The complete refreshed frontend suite passes **520 tests / 95 files**, and
ESLint passes. The ordinary build retry failed in unchanged Next/Google Font
loading when a font download timed out. No external retry is authorized. The
exact cached font binaries and source-map CSS are preserved with hashes under
`coverage/correction-sep8/cached-fonts/`; a separate production build **passes** using Next's font-response injection
and those exact assets served on loopback, with OS-level non-local outbound
network denial. This is explicitly cached-font build evidence, not a claim that
the ordinary external font-fetch dependency is available. Product font files,
font choices and dependencies remain unchanged. The temporary loopback font
server was stopped after the successful build.

The initial diagnostic rerun was interrupted before completion to impose the
same OS-level non-local outbound network denial; its partial log is retained as
`other-review-partial.log` and is not acceptance evidence. The faithful
153-file / 2,526-test rerun is active in the same order with that denial and
the cached-font response map. The loopback-only font server was restarted for
this run and must be stopped when it finishes. The original failed run is
preserved as `other-first.{log,data,exit-code}`; current outputs are
`other.{log,data,exit-code}`. The unchanged migration pass remains valid.
Frontend coverage/lint and the cached-font production build now pass for the
small diagnostic source change. `source-hashes-review-fix.json` binds the rerun
entry. Reconcile coverage provenance after this stabilizes; do not use the
previous receipt as evidence for changed diagnostic bytes. Resolve this finding
within the same sole review cycle before Macro B; no new reviewer is authorized.

The network-restricted full rerun finished: **2,509 passed, 11 failed, six
setup errors**, with the W403B Start/End browser journey passing in its faithful
aggregate position. Its immutable outputs are now
`other-network-restricted.{log,data,exit-code}`. The runner's outbound restriction
also denied local Unix sockets: Docker-dependent checks and GPG could not reach
their local services. The corrected `local-only.sb` allows loopback IP and local
Unix sockets while still denying other outbound network access. All **11 failed
checks pass** unchanged under that corrected profile (`sandbox-socket.log`).
An initial focused selector truncated one parameter containing a space; its
collection error is retained separately and is not test evidence. The six
frontend-image setup errors remain to be reverified; production/test bytes have
not changed. The standard image build has no cached-font injection interface,
so an explicitly offline image-build probe is checking available local build
inputs before deciding whether external dependency access is mandatory.
Do not claim a green full shard, refresh final coverage provenance, accept A,
or start B from these partial/complementary results. The owner requested no
continuous output polling; completion is awaited without repeated log reads.

**Remaining mandatory local evidence / external-access decision:** the isolated
standard-Dockerfile probe used the already-cached pinned Node image, the legacy
local builder (avoiding registry metadata resolution), `--pull=false` and
`--network=none`. It failed at `npm ci`: uncached pinned package downloads cannot
resolve in that isolated build (`offline-image-probe.log`,
`offline-image-npm.log`, repeated `EAI_AGAIN`). This does not claim that the
separate BuildKit dependency cache is absent. The unchanged standard frontend
build additionally needs Google Font responses, as the earlier normal-build
failure demonstrated; only the explicitly injected cached-font build has
passed for the new diagnostic bytes. The standard Dockerfile has no such
injection. A read-only dependency-download allowance is therefore requested
before running the standard image verification; the owner's prohibition on
external contact remains in force until answered. No production, provider,
publication or deployment action is requested. The stopped probe container and
its two new intermediate images were removed; the owned loopback font server
was stopped. Other task-owned local services and all evidence remain available.
On allowance: verify the six image cases, complete the faithful corrected
non-migration run, refresh coverage from accepted evidence, and obtain bounded
resolution from the existing Sol/medium reviewer. A remains unaccepted, B
unstarted, and no handoff or additional reviewer is authorized by this pause.

**Owner amendment, 8 Sep — review evidence before download authorization:**
Unrestricted internet access is not a default remedy. Present the aggregate-
position browser pass and the corrected 11 local-socket passes to the existing
Sol/medium reviewer in its same review cycle. Ask whether the original P1 is
resolved and whether the six exact standard-Docker-image checks may remain an
explicit external dependency-availability gate. Explain both the original Unix-
socket setup failures and the separate offline npm/Google Font limitations;
neither substitutes for a successful exact image rebuild. Do not construct
substitute evidence, change product code or tests, or start B unless the reviewer
accepts this treatment. If it requires a green exact shard, return to the owner
for narrowly scoped, one-run download authorization. This supersedes the
preceding proposed allowance-first next step. Dispatch remains **GPT-5.6 Sol /
medium**, explicitly owner-selected for this same bounded review resolution;
ownership is read-only and no additional agent may be created.

**Future reproducibility candidate — outside this programme:** when separately
authorized reproducibility work is planned, assess the standard frontend build's
Google Font download dependency and an approved reproducible asset/cache policy.
Evidence: `frontend/src/lib/fonts.ts`, `frontend/Dockerfile`, and
`coverage/correction-sep8/build-review-fix.log`. This records a future candidate
only; it authorizes no font, dependency, Dockerfile or product change in C01–C37
or H07 and creates no new executable queue item.

**Same-review resolution — Sol/medium, 8 Sep:** the reviewer explicitly resolved
the original browser P1 using the diagnostic red/green and aggregate-position
pass. It accepted the six unchanged exact standard-image cases as an external
dependency-availability gate for Macro-A acceptance, without release/deployment
readiness. It does not require another full non-migration run: 2,509 aggregate
passes plus 11 corrected local-socket passes account for all other cases. Its
remaining FIX was only the stale coverage/provenance receipt; no product change
or substitute image evidence was requested. This replaces the earlier local
requirement for a green exact shard; the image gate stays explicitly open.

The controlled C36 receipt now uses only current accepted executions:
`migrations.data`, `other-network-restricted.data`, `sandbox-socket.data` combined
as `accepted-macro-a.data`, plus the current 520-test frontend LCOV. No earlier
image result, interrupted run or synthetic coverage was substituted. Refresh
and separate provenance verification both pass in
`coverage-resolution-{refresh,provenance}.log`: changed **94.291% line /
88.6076% branch**, global **87.1919% / 64.1092%**, backend **91.5781% /
77.2429%**, frontend **63.149% / 47.3804%**. Trusted D32 floors, policy hash,
eligible inventory and instrumentation remain unchanged by this resolution.
Source fingerprints match except the generated Playwright result receipt;
diff whitespace validation passes. The same reviewer receives this bounded
receipt reconciliation for final acceptance; no new review agent or broad
verification run is authorized or needed.

**Macro-A accepted — same Sol/medium review PASS, 8 Sep:** all seven final
receipt/input hashes matched; controlled refresh and independent provenance
verification resolve the last FIX. The reviewer expressly requires no further
exact non-migration run or local implementation change before B. Original
browser P1 is resolved; six standard-image cases, C34 and existing external
gates remain open. Exactly one implementation-review agent has been used;
the one fresh final specialist/consolidated reviewer remains reserved after B.

**Macro-B entry assessment:** the existing Astra controller retains the accepted
source, contract, ownership and evidence pointers without unresolved repository
conflict or missing product decision. Context and operating performance remain
adequate for direct implementation; completed A alone is no handoff reason.
Continue P06 here under the original reviewed acceptance contract. All sixteen
Macro-B C IDs remain individually `VALID / PLANNED` until demonstrated. No
implementation subagent, second Astra writer or external network allowance is
created by this promotion.

**P06 / C06 demonstrated:** one revoked-admin prefix regression failed against
the original service, leaving the authorized 101st intent pending. Restoring
only the baseline selector in memory makes all four PostgreSQL/SQLite ×
revoked-admin/unexpected-error cases fail; the corrected 29-test worker/R20/R21
suite passes, including durable claim-before-provider, uncertain recovery,
concurrency, migration guards and final authorization. The first fixture used
an invalid user status and was corrected before useful red evidence; its log is
retained separately. Evidence is `coverage/correction-p06/c06-{red,
selection-mutation-red,focused-green}.log`, with coverage in `c06.data`.
The scheduler reuses immutable `worker.payout_submission.failed` audit events
and sorts by the later of intent progress and failure time. It does not bypass
the intent's database transition guard, add a migration, fabricate provider
attempts or change claims/payment history. Failure metadata/logging includes
only the error code/class, never exception contents; failure-journal persistence
errors propagate rather than pretending durable progress. All four cases retain
the 100 denied intents at generation zero, make no provider attempt for them,
and process the later authorized intent on the next bounded sweep. Focused Ruff
and scope inspection pass; final integrated coverage and specialist review
remain reserved for stabilized Macro B. C19–C23 remain independently planned.

**P06 / C19 demonstrated:** six baseline cases lose unresolved flags on newest-
member regrouping, signature departure or insufficient evidence. Removing both
automatic-deletion helpers preserves the original flag ID, evidence, detection
time and authoritative money hold. A seventh baseline-source mutation fails the
PostgreSQL money-lock race's strengthened retained-hold assertion. The corrected
78-case replay/hold/assessment/earnings-release suite passes, including both
existing cross-trip concurrency cases and governed dismissal/redetection.
Evidence: `coverage/correction-p06/c19-{red,concurrency-red,accepted-green}.log`
and `c19-accepted.data`. The intermediate 77-pass/one-failure run exposed one
remaining old test expectation that required deleting the hold after the lock
released; it now requires both exact hold owners and preservation of the original
flag/evidence. No assertion was removed or concurrency barrier weakened.
Latest-member detection, bounded/redacted evidence and review semantics remain;
no migration, reconstruction of previously deleted history or new fraud policy.
Scoped Ruff/diff inspection pass.

**P06 / C20 and C21 demonstrated:** the completed payout/trip complement passes
**99 tests** (`coverage/correction-p06/c20-c21-focused-green.log`, coverage
`c20-c21.data`). C20's baseline produced three failures and one preserved
boundary pass; the corrected four cases pass. Earlier ended/unsealed trips
retain chronological daily-cap authority across mixed prices; an end exactly
at Lagos midnight does not consume the next day. C21's baseline admitted the
pre-start trip (one failure, two boundary passes); frozen-start minus one
microsecond now rejects without creating a trip, while exact start and later
admit through the full production authority. Existing v2/v3 calculations,
correction conservation, exclusive end and mutable campaign checks remain.
Evidence: `c20-{red,green}.log`, `c21-red.log` in the same directory. Focused
Ruff and complete four-file scope inspection pass; no migration or API shape
change. C22/C23 remain individually planned.

**Owner amendment — one bounded standard-image verification execution:** run
only the six existing cases in `tests/test_rel005_frontend_image.py` and their
ordinary image build, with dependency access limited to the pinned base image,
locked npm packages and existing Google Fonts. No dependency changes, substitute
build, font redesign, publication or deployment. Record command, exact revision
and worktree, available image/dependency identities, downloads, complete log
and result. If unavailable dependencies still block the build, retain the exact
failure and six-case external gate; do not bypass assertions or retry beyond
this one-run authority. The separate Google Font reproducibility candidate
remains outside this programme. Host test execution retains the local-only
network sandbox; only the ordinary Docker build's dependency retrieval is
permitted. Final review remains the one reserved fresh Sol/medium agent after
Macro B and integrated evidence stabilize.

**Bounded ordinary Docker verification — PASS:** the six existing cases in
`tests/test_rel005_frontend_image.py` passed, with no skips, in **24.84s**.
This is one configured production-image build and six cases, not six images.
Compiled map/revision survive; runtime map override cannot replace the artifact;
all four missing/changed expected map/revision checks reject. The unchanged
ordinary Dockerfile ran npm build; no font mock, alternate Dockerfile, dependency
change or test substitution. Complete evidence: `coverage/correction-docker/`:
`command.txt` records the exact command, `entry.json` the unchanged baseline SHA
and full entry worktree plus input hashes, `tests.log` the six results, and
`docker-complete.log` every Docker command, complete build output, image inspect,
history and fixture cleanup. `locked-dependencies.json` preserves every available
resolved npm version/URL/integrity from the lockfile.

Base identity remains
`node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`;
BuildKit resolved registry metadata and reused its base and npm-ci layers.
No uncached npm packages or base layers were downloaded in this run. Fresh
Next 16.2.10 production compilation passed with the existing Google Font
arrangement; the log does not expose individual font HTTP requests/cache hits,
so a per-font download inventory is unavailable. The build excludes host
`.next` and `node_modules`; no host font cache or mock was injected.
Output image index
`sha256:b1b4b4ee00e885a2cbca423d6f44330dbdd48757eab4ef3a7c6703687e52d94a`,
platform manifest
`sha256:613392d7c67d49c935d4a479a5ba05d860d4564a1343486fe71deb10999e6500`.
The fixture removed its image. A nonfatal existing Big Shoulders fallback-font
warning remains in the complete log. This closes the six-case execution gate
for these audited inputs; subsequent frontend changes require their affected
checks. It grants no deployment/release acceptance. The one-run download
authorization is consumed; unrelated outbound activity remains blocked and
Google Font reproducibility remains a separately deferred candidate.

**P06 / C22 and C23 demonstrated — P06 locally accepted:** all **108** focused
report/measurement/privacy/publication/adjacent-day correction cases pass,
including real PostgreSQL report-first and correction-first overlap. The
127 preserved queue/protocol/PWA/tracker/BFF fixtures also pass; OpenAPI's two
JSON artifacts remain byte-synchronized, with no public DTO shape change.
New runs freeze signed ledger facts, retain original gross-calculation
provenance, and use terminal-period membership consistently in metrics,
daily totals, frozen reports and privacy contributor history. Credits/reversals
remain separately privacy-bounded; voided entries and debt-remainder provenance
cannot double-count cost. Missing calculated-trip ledger authority blocks.
Historical v1 formula reproduction, issued runs and original calculations remain
unchanged; exact retry/repeated source hashes converge.

Three initial PostgreSQL cases reproduced the original correction/cross-period
failures. Seven tests fail with the baseline measurement module restored only
in memory; restoring the baseline report module as well reproduces the eighth,
missing-ledger failure. Added overlap evidence exposed Campaign/Trip inversion
when a correction writer owns Trip before its ledger insert acquires Campaign
FK authority. New issuance takes the existing campaign-terms lock before active
admin and disclosure snapshot locks, matching the production money writer's
ordering. Both directions now finish within the bounded barrier and expose
exactly one old/new ledger position. No lock was weakened, migration added,
financial history edited or external method approval invented.

Evidence: `coverage/correction-p06/c22-c23-{red,authority-mutation-red,
accepted-green}.log`, `c22-missing-ledger-red.log`,
`c22-c23-accepted.data`, `pwa-contract-green.log`, `openapi-check.log`.
Intermediate logs retain the discovered deadlock, a corrected missing test
import, and the initial 102-pass complement; only the final 108-pass run is
accepted for these inputs. Scoped Ruff and diff whitespace/scope inspection
pass. Final integrated coverage and the reserved consolidated specialist
review remain outstanding. All six P06 IDs are independently demonstrated;
P07 now owns C24–C28, and P08 remains unstarted.

### P07 — C24–C28 locally demonstrated (8 September)

C24/C25 persist one exact End manifest (or legacy watermark) before sending,
serialize it with queue writes and receipts, and fence capture preparation,
visibility callbacks and late GPS callbacks by End phase and generation.
Same-page ambiguous End flushes the current trip before reconciliation; reload
retries the durable End without reopening capture. Failed durable End storage
retains evidence and fails closed. C26 reconstructs cancellation independently
from immutable cancellation events and the assignment cutoff; before-cutoff
samples survive, exact/after-cutoff samples cannot enter through ingestion or
quarantine review. No deactivation history is invented.

C27 uses heading [0,360) in the BFF and normalizes invalid optional sensor values
before enqueue/hash, preserving valid peers. C28 stores signed per-sample
results atomically with batch settlement, validates their counts/identity,
shows accepted/rejected/quarantined evidence separately and retains diagnostic
receipts across reload without retransmitting settled batches.

Evidence in `coverage/correction-p07/`: `end-red.log` (3 reproduced failures),
`partial-heading-red.log` (5), `legacy-end-red.log`, `partial-reload-red.log`,
`unit-boundary-red.log` (4 minimal-mutation failures with source restored),
`c26-precise-history-red.log` (3 baseline failures), and
`browser-mutation-red.log` (all 3 browser regressions fail under restored unsafe
boundaries). Green: `final-pwa.log` **141 passed**, `c26-final-green.log`
**63 passed**, `browser-final-green.log` **3 passed**, plus type/lint, scoped
Ruff and diff checks. `browser-partial-retained.png` visually inspected.
Browser cases use actual Next/IndexedDB/WebCrypto/Web Locks with explicitly
synthetic GPS/server receipts; PostgreSQL tests exercise real backend receipt
and cancellation authority. No physical GPS, device or provider claim follows.
No migration or public contract shape changes. P07 diff reviewed for scope;
A's accepted diagnostic source remains preserved. P08 now owns C29–C33.
Final integrated coverage and the reserved fresh Sol/medium review remain due.

### P08 — C29–C33 locally demonstrated; integrated verification open (8 September)

C29's two forms bind uploaded IDs and upload request IDs to exact File objects
and access context. Changed form generations reject stale async completion;
unchanged retries retain the original request/body and cached IDs. Person-form
success resets its captured form element safely after asynchronous work.
C30 shares current-approval convergence under the locked application and work
eligibility authority on person/payee and vehicle decisions and exact retries.
Vehicle retry still replays its original immutable decision, but current
eligibility alone controls convergence. Normal person-first submission remains;
review-order tests use an explicitly seeded expired prior-person projection and
an allowed replacement submission. No expiry worker is invented by that fixture.
Approval does not activate the invited user or duplicate review/terminal audits.

C31 keeps a successfully created campaign ID in the recovery URL. Retry uses
only the existing creative-attachment API; exact managed-file retry already
converges there. Reload and campaign detail expose creative-only recovery;
basics cannot be reopened for editing through this flow. After reload, reselect
only missing creative files; already attached items remain on campaign detail.
An actual browser also exposed Continue's button-type transition submitting the
form before explicit review confirmation. Preventing that default click action
preserves the explicit Create/Attach step; no broader wizard redesign was added.

C32 supplies the ordinary local demo's frozen legacy-compatible payout binding,
synthetic financial reservation, immutable activation snapshot and time-limited
installation/display-proof records. It consumes the unchanged production Start
checks; no auth, evidence or money bypass was added. Fictional identity/account
values use actual configured envelope encryption. These records are explicitly
synthetic fixtures, not real bank verification, provider objects, credit approval
or physical installation evidence. Existing frozen/history rows survive reruns.
The R59-only authority insertion block is removed; its existing preflight now
checks the ordinary seed. Live gates and normal configured evidence-policy
requirements remain. No external provider connection is made by this seed work.

C33 isolates unexpected email-item failures with sanitized warning/audit evidence.
Due ordering includes the durable last unexpected failure so a persistently
failing oldest prefix rotates. Uncertain claims remain untouched until expiry,
then recover even above the normal handled-failure cap with the same provider
key. A failed failure-journal commit propagates. The job remains selection and
composition only; domain helpers own failure history and its ordering expression.
The architecture test retains its exact import and forbidden-write checks with
the two newly required domain helper names. Notification audit targets resolve
to the exact recipient under C14 without importing another tenant's events.

Evidence under `coverage/correction-p08/`: C29 `c29-red.log` (7 failures/1 pass),
`c29-green.log` **9 passed**; C30 `c30-final-red.log` (3 failures/1 pass),
`c30-final-green.log` **31 passed**; C31 action/UI red logs (2 failures each)
and `c31-first-green.log` **6 passed**; C32 `c32-red.log` reproduces production
Start rejection and `c32-full-green.log` **22 passed**, including migrated
immutable guards, rerun preservation and ordinary API Start/End; C33
`c33-final-red.log` (4 reproduced unexpected exceptions) and
`c33-final-green.log` **68 passed**, including PostgreSQL/SQLite fairness,
claim recovery, durable recipient relationships and worker process recovery.
`browser-mutation-red.log` reproduces all three C29/C31 scenarios against the
unsafe boundaries; all source is restored and `browser-final-green.log` reports
**3 passed**. Initial fixture mistakes and the caught architecture-placement
failure remain in their original logs and are not accepted evidence.

P08 introduces no migration or public API shape change. Type/lint and focused
Ruff pass before final integration. `coverage/correction-final/` records fresh
input hashes, exact commands and full logs for the aggregate backend/frontend
checks. The six Docker cases retain their already-recorded bounded six-pass
receipt; that earlier image does not contain subsequent B frontend edits, and
no second dependency-enabled image build has been authorized. No final review,
release or deployment acceptance is claimed yet. The sole reserved fresh
Sol/medium final specialist/consolidated review may start only after integrated
evidence stabilizes; all substantive findings must be resolved in this session.


### Integrated verification — in progress (8 September)

Fresh migrations: **195 passed** in `coverage/correction-final/migrations.log`;
exact command, input hashes and coverage data are adjacent. The remaining backend
aggregate initially stopped at collection because a pre-existing dispute test
imported C19's deleted automatic-removal helper. That test now invokes the detector
and still asserts preservation of the exact disputed flag and its evidence;
`disputes-final-green.log` passes all 8 dispute tests. The original collection
failure is retained as `other-collection-failure-other.log`. The full aggregate
is running again without omitting that module or reducing an assertion.

Frontend: **554 passed / 98 files** in `frontend-final-green.log`, with final type
check passing. Two added frozen-End protocol regressions fail under the isolated
missing-retry mutation (`tracker-restored-final-red.log`) and pass with the exact
implementation. C31's recovery-page authorization/unavailability regression adds
5 observed baseline failures plus the unchanged normal-create case
(`coverage/correction-p08/c31-page-red.log`). The initial V8 LCOV contained a
negative branch count and was rejected by the unchanged coverage checker; its
raw input is retained in `frontend-first-invalid.lcov`. Explicitly pairing the
selected End protocol's request with its completeness value removes that
instrumentation ambiguity; the measured LCOV now parses strictly. No coverage
count was rewritten, branch excluded or floor weakened. Final lint, regenerated
OpenAPI byte check and repository Ruff pass; final combined coverage remains due.

Integration complements now pass: **28** dispute/cancellation/payout-worker/email
cases (`integration-complement.log`) and **9** R08 authorization cases
(`r08-integration-green.log`). C26's older cancellation test now proves one valid
pre-cutoff sample plus one signed post-cancellation rejection, exact receipt
retry and preserved historical financial cutoff; omitting cancellation authority
makes it fail (`c26-integration-red.log`). The current architecture distinguishes
previously retained non-economic evidence from newly unauthorized capture.
The two C06/C33 logging probes reproduce Alembic fileConfig's disabled imported
logger state (2 failures in `logging-isolation-red.log`); each test now restores
only its own logger with scoped monkeypatching, and the same probe passes both
(`logging-isolation-green.log`). Product logging and all fairness/audit assertions
remain unchanged. R08's measurement argument is now a valid typed request so it
can acquire the required campaign-terms lock before active-admin authority;
all 44 call sites, denied-without-mutation checks and the three PostgreSQL
serialization directions remain covered without weaker barriers/assertions.
The accepted final tracker also passes all three real-browser fault scenarios
(`offline-browser-final.log`); coverage, request signatures and receipts remain
unaltered by the diagnostic/mutation harnesses. The full backend shard finished with **2,542 passed / 12 failed** in 42m01s,
with no skips. Its 12 failures are exactly the older C26/C33 expectations,
C06/C33 imported-logger isolation and R08's untyped measurement placeholder
recorded above; all affected complete modules now pass in the **28 + 9 + 41**
integration complements. The final 41-case worker/email complement also retains
first/third-item completion, uncertain second-item claim and same-key expiry
recovery; baseline email-sweep restoration fails that regression
(`email-worker-red.log`). No product safeguard was weakened to satisfy an old
expectation. This is a completed aggregate with resolved focused complements,
not a claim that the raw 2,554-case shard was entirely green in one invocation.
The aggregate-position W4 browser and local-socket cases pass in that same shard.

Final combined coverage (`coverage-verified.json`): changed **95.4325% lines /
87.8623% branches**, global **87.5272% / 65.2964%**, backend **91.6353% /
77.4003%**, frontend **65.6889% / 50.2389%**. C36's controlled refresh records the
current complete inventory and source/policy hashes only after the trusted
ancestor floors and unchanged 90/80 changed-code ratchet pass; a second strict
provenance check passes. The complete measured inputs and combine/refresh logs
are retained under `coverage/correction-final/` rather than pasted here.

The ordinary host production build was attempted with outbound access blocked
and failed retrieving the existing Google Fonts (`frontend-build.log`). No font
substitute, dependency change or additional download permission was used. The
already-accepted six Docker cases remain tied to their earlier exact input
manifest, not to later B frontend changes. Final-image execution, C34 and the
existing live/device/provider/legal/release gates remain explicit for the final
review. All nine pre-existing untracked file hashes remain unchanged
(`preexisting-preservation.json`); HEAD and baseline remote ref are unchanged,
branch `master`, staged index empty. The controller has inspected the complete integrated diff scope. The reserved
fresh Sol/medium final specialist/consolidated review is now admissible; its
verdict and any remediation remain due.


**Reserved final review dispatched:** `/root/final_integrated_review`, fresh
GPT-5.6 Sol / medium, 8 September. The owner explicitly mandates this model and
reasoning for the complete security/privacy/money/migration/concurrency/storage/
recovery specialist and consolidated review. Ownership is read-only over the
unchanged approved contract, full integrated diff, 170-file manifest, evidence
and gates; no implementation or nested agents. The controller remains the sole
Astra writer. This uses the second and final implementation-review slot; any
substantive remediation returns to this same reviewer, not another dispatch.
`coverage/correction-final/` holds the exact review packet and final provenance
receipt. Only this review-status ledger entry changed after dispatch; no product
or acceptance criterion changed. The first returned report stated PASS/no implementation findings and accepted
the explicit final-image/C34 release gates, but several canonical descriptions
were misassigned (including C13, C22–C25, C28, C37 and H07) and five artifact
paths were inaccurate. The controller withheld acceptance of that written
record and returned it to the **same Sol/medium reviewer** for source/test-cited
C01–C37/H07 and exact 30-artifact reconciliation. This continues the same final
review cycle; no new agent or product edit is authorized or created by it.
The corrected source/test-cited response is **PASS, no findings, no local
acceptance-blocking verification gap**. It individually reconciles all C01–C37
and H07 and the exact 30 added paths/consumers/lifecycles. The corrected record
supersedes the initial labels; condensed receipt is
`coverage/correction-final/final-review.md`. The reviewer explicitly accepts
final-source image/dependency availability and C34 as release/external gates,
not local defects, and requires no additional local implementation or shard
before acceptance. No third implementation-review slot was used.


**Local implementation acceptance — 8 September:** Macro A's accepted Sol/medium
PASS and Macro B's corrected final specialist/consolidated Sol/medium PASS are
preserved. Every canonical row above is reconciled: C01–C33 and C35–C37 are
`VALID / IMPLEMENTED`; C34 is `EXTERNAL VERIFICATION REQUIRED`; H07 is implemented.
The six duplicates create no additional work. All owned local behavior is
demonstrated and no actionable review finding remains. This does not mark the
entire correction programme, original executable queue, release or deployment
complete. The original queue/controller authority is unchanged.

Confirmed invariants remain: immutable financial/review/audit/issued-report
history, active-admin/password/session authority, current privacy/consent,
exact storage origins, ordinary fail-closed readiness, stable provider claim
keys, accepted payout windows and screen-on-only evidence capture. No unresolved
local evidence is discarded. No dependency, font family/theme or Dockerfile
change, external provider action, commit, push, merge, PR, release or deployment
has been performed. Nine pre-existing untracked hashes remain unchanged.
Final scope is **140 tracked changed files + 30 new owned files**, with the nine
original untracked artifacts excluded. HEAD and origin baseline remain
`00918531b2bb37a1d184d1d4f917f659b9e4d80b`, branch `master`, empty staged index.

Remaining gates: exact final-source image and normal Google Font-dependent host
build; accepted capable predecessor/positive forward-schema rehearsal for C34;
separately owner-authorized commit/exact-SHA CI/final R59 execution; real device/
GPS, live provider/IAM/CORS, legal, staging and pilot evidence. The bounded six-
case Docker receipt remains valid only for its recorded earlier inputs. No new
unrestricted or dependency-enabled network permission is inferred. Google Font
reproducibility is the separately deferred candidate, requiring future owner
prioritization; font consolidation, theme selection and redesign remain outside
this programme. Local behavior is reviewed with no known actionable defects;
release-ready **NO**, deployment-ready **NO** while these gates remain.

**Direct owner authorization — post-remediation finalization (8 September
2026, recorded before any edit):** the owner directly authorizes, outside the
Executable package queue and without reprioritizing it: complete the deferred
frontend font/build reproducibility correction without changing approved visual
behavior; verify the ordinary final-source host and Docker builds; commit the
accepted programme; push `master` only as a verified non-force fast-forward;
then obtain exact-SHA CI and final R59 evidence. Dependency-enabled access is
limited to exact pinned lockfile dependencies, pinned base images and
acquisition of exact retained font assets with compatible licensing. The nine
pre-existing untracked provenance artifacts stay untouched and unstaged. C34 and
the live device/provider/legal/staging/pilot gates remain external and are not
owned here. No deployment, release, PR merge or production infrastructure change
is authorized.

**Font/build reproducibility correction — evidence (8 September 2026):** the
frontend production build no longer contacts Google Fonts. All seven Google
families remain retained because `globals.css` maps each to a retained theme
(Inter to daylight-ops and broadside, Fraunces to ivory-ledger, Bricolage to
danfo, Archivo to hi-vis, Poppins to terra-grain and the Terrax landing, Big
Shoulders to broadside, IBM Plex Mono to the base mono role and coverage), so no
family, weight or style was dropped and no theme was selected. `next/font/google`
treats `subsets` as a preload filter only, so the approved output is 46 faces;
all 46 exact binaries already existed under
`coverage/correction-sep8/cached-fonts/`, every sha256 re-verified against
`hashes.json`, and all 46 independently re-fetched from `fonts.gstatic.com` and
found byte-identical (`live-refetch-comparison.json`). They are vendored to
`frontend/src/fonts/google/` with per-family SIL OFL 1.1 texts under
`google/licenses/` and `google/provenance.json` binding each file to its family,
subset, weight, unicode-range, exact upstream URL and hash. Seven modules in
`frontend/src/fonts/families/` declare them through `next/font/local`, one call
per family and subset because `declarations` applies to every `src` entry; the
root and landing layouts now set the same CSS variables inline. No dependency,
font CDN, Dockerfile, `globals.css` token or theme changed, and
`package.json`/`package-lock.json` are untouched.

Verification: the guard `frontend/src/fonts/vendored-fonts.test.ts` fails 3 of 92
at the pre-fix boundary and passes 92 of 92 after
(`guard-red.log`, `guard-green.log` inside `static-checks.log`). Five one-at-a-time
source mutations — a duplicated face name, a preloaded non-latin subset, a metric
fallback added to Big Shoulders, a metric fallback removed from Fraunces and an
altered Inter unicode-range — are each detected by the specific guard that names
them, and every mutated file was restored byte-identically
(`guard-mutations.log`). The ordinary production build passes with all outbound
HTTP and HTTPS forced through a dead proxy (`frontend-build-offline.log`), and no
`fonts.googleapis.com` or `fonts.gstatic.com` string remains anywhere in `.next`.
A mechanical comparison of every built `@font-face` against the cached Google
baseline, keyed by binary sha256, reports 46 of 46 faces emitted exactly once
with zero drift in weight, style, `font-stretch`, `font-display` or
`unicode-range`, zero family-name collisions and the same latin-only preload set
(`face-tuple-comparison.log`). Eight metric-fallback faces are emitted — Clash,
Satoshi and six vendored families; Big Shoulders correctly has none, matching
`next/font/google`, whose metrics table has no entry for it, and Fraunces
correctly keeps `local(Times New Roman)`. Those override values are now computed
from the vendored binaries instead of Next's precalculated table, so they differ
marginally; this affects pre-swap metrics only, not painted glyphs. Browser checks
against the production server confirm each of the nine themes resolves to its own
typeface, that hi-vis retains `font-stretch: 125%`, and that Yoruba and Hausa text
under hi-vis lazily loads the Archivo latin-ext and vietnamese faces, which a
latin-only vendoring would have lost. 99 frontend files and 646 tests, typecheck
and lint pass. Two defects were found by verification and fixed: the first
implementation reused subset const names across families, which `next/font` turns
into one shared `@font-face` family and which merged all seven typefaces, and the
first guard version accepted a missing metric fallback and a non-latin preload
target. Both are now asserted and mutation-proven.

Final-source image: the six `tests/test_rel005_frontend_image.py` cases pass
against the frozen final source recorded in `final-source-identity.txt`
(`rel005-final-source.log`), superseding the earlier image receipt, which is not
represented as final-source evidence. A separate inspection build of that same
source shows 52 woff2 in `/app/.next/static/media` — 46 vendored plus the six
pre-existing local faces, 34 of them non-latin subsets — zero Google host
references anywhere in `/app/.next`, and the P07/P08 frontend markers present
(`image-content-inspection.log`). Base image `node:22-alpine`
`sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`,
linux/arm64. The production CSP already sets `font-src 'self' data:` and
`style-src-attr 'unsafe-inline'`, so the vendored faces and the inline variables
are both permitted. No contract or generated-artifact input changed, so no
architecture section 9 baseline or R14-B fixture rerun was required. An
independent plan review and an independent post-build minimal-change review were
both obtained and reconciled; the post-build review's P1 finding — that the
typecheck and lint receipts predated the final source — was fixed by re-running
both, which then surfaced three real type errors in the strengthened guard.
Evidence logs are retained under `coverage/correction-fonts/` and are not
committed. The nine pre-existing untracked artifacts remain untouched and
unstaged.

**Exact-SHA CI and R59 — NOT ACCEPTED (8 September 2026):** the programme was
committed once as `bc3c3454f489ba4cc5b4a6c6f56cc3fafe4b90ff` and published to
`origin/master` as a verified non-force fast-forward `ff2225a..bc3c345`, 500
commits ahead and 0 behind, with `origin/master` proven an ancestor. GitHub run
`34276581120` ran against that exact SHA — each job's own SHA-verification step
passed — and **concluded failure**. `lint / types / unit / contract / build`
passed, covering the frontend build, type, unit and generated-contract gates.
`backend lint / tests` failed with 14 failed and 2741 passed in 70m47s. The R59
real-stack release journey failed. `changed-code coverage policy` and `e2e
against the real stack` were **skipped**, because they depend on the backend job,
so those two required gates did not execute and are unevidenced for this SHA.

R59 is not environmental. After the simulated API outage and recovery the
`End trip` control never re-enabled, with the tracker showing `degraded`,
`Pings synced 0`, `Buffered 3` and GPS `Waiting…`. The API container log records
exactly one `POST /api/v1/driver/trips/start` `201 Created`, normal
`trips/current` polling, and no `POST .../pings` or `POST .../end` at all. **The
absent ping POSTs are not themselves the defect:** `FLUSH_INTERVAL_MS` is 15s and
`FLUSH_AT_COUNT` is 20, and the journey's healthy window is roughly six seconds
carrying about three pings, so no flush is due before the outage begins. An
earlier revision of this receipt wrongly presented the quiet healthy window as
evidence of the regression; that reading is withdrawn. The
backend and worker logs show no traceback, no 5xx and a normal SIGTERM teardown,
and the Playwright trace records no console error and no page error, so the app
was hydrated and interactive. R59 **passed** at baseline `0091853`. The failing
assertion is the post-recovery `expect(End trip).toBeEnabled()`: after the
outage-time End freezes the durable boundary, a reload hydrates the tracker into
`endPhase = "submitted"` with `authorityUncertain` set and returns before the
runtime is re-probed, so `assessPilotPwa` never sees `session === "valid"` again
and both the `Reconcile trip` and `■ End trip` affordances stay disabled. The
governed `frontend/e2e/r59-real-stack.spec.ts` is byte-unchanged in this commit,
so the End/recovery affordance changed underneath an unchanged journey. R59 runs
with `retries: 0` by design. This is recorded as a genuine implementation defect
in the P07/P08 frontend correction, surfaced only by exact-SHA CI. No product
code was changed to force green and no further push was made from that state.
Evidence: `ci-exact-sha.log`, `r59-error-context.md`, `stack.log`,
`compose-ps.txt`.

All 14 backend failures pass locally; 11 are demonstrated environmental and 3 are
CI-only with undetermined cause. Demonstrated environmental: the eight
`test_storage_csp_origin.py` cases fail in CI with `ConnectionResetError [Errno
104]` while all eight pass locally in 5.28s against the real Docker-launched
`caddy:2.8-alpine`, so the CI failure is runner container networking; the two
`test_errors.py` R13 budget cases took 6.28s and 9.33s against a 3.0s budget
under `coverage run` on a hosted runner and complete locally in 1.40s; and
`test_recovery_readiness_authority.py::test_historical_predecessor_rehearsal_fails_before_build_or_infrastructure`
fails on `fatal: ambiguous argument '26f5e221…^{commit}': unknown revision`
because the predecessor commit is absent from the CI checkout depth, which is the
C34 external-gate area. Undetermined: the two PostgreSQL cases
(`test_driver_vehicle_approval.py::test_postgres_nin_rewrap_and_trip_share_eligibility_before_profile_order`
expecting `DRIVER_PROFILE_NOT_ACTIVE` but observing
`DRIVER_PERSON_PAYEE_NOT_APPROVED`, and
`test_r20_disbursement_postgresql.py::test_concurrent_claim_commits_before_provider_io_and_submits_once`
observing `query_only` instead of `resolved`) both pass in isolation locally
against a real PostGIS 16-3.4 but fail inside the full CI suite, which points at
ordering-dependent cross-test state rather than an isolated defect; and
`test_w403a_release_preparation.py::test_bundled_tls_rejects_wrong_san` passes
locally but does not raise in CI, which points at platform-dependent TLS SAN
validation. None of these three is demonstrated environmental and none is
reproduced as a product defect, so all three also return to the correction gate.
Evidence: `backend-failed.log`, `local-triage.log`, `local-pg-triage.log`,
`local-csp.log`.

The consolidated post-build minimal-change review of the font/build amendment was
dispatched but never returned a verdict before the session ended; an earlier
revision of this receipt wrongly reported it as obtained and reconciled. That
review is outstanding and is folded into the corrective package's consolidated
review. The repository is therefore **not CI accepted**, **not release-ready**
and **not deployment-ready**, and the font/build amendment's local acceptance
rests on its plan review and verification evidence pending that consolidated
verdict. C34 and the live
device, provider, legal, staging and pilot gates remain external and unmet. This
receipt is written for the next corrective commit; no evidence-only commit was
created for it.

**Direct owner authorization — exact-SHA acceptance correction (9 September
2026, recorded before any edit):** the owner directly authorizes one
Review-Required corrective package, forward-only from
`bc3c3454f489ba4cc5b4a6c6f56cc3fafe4b90ff`, covering (A) the genuine R59 ping
submission/recovery regression and (B) the exact-SHA CI failures blocking
backend, changed-code coverage and real-stack e2e acceptance. No revert, reset,
history rewrite, force-push or additional implementation branch; `origin/master`
is corrected forward only. The accepted font/build work is not to be disturbed.
No implementation subagents; one review-only agent per gate. Environmental CI
failures must be fixed at the real boundary — no weakened assertions, skipped
tests, unevidenced timing relaxations, or mocked-away Caddy/PostgreSQL/TLS — and
anything that cannot be reproduced or confidently classified is retained as
explicitly unresolved rather than guessed. C34's genuinely capable predecessor
and the physical-device, provider, legal, staging and pilot evidence remain
external and unauthorized, as do release and deployment.

**Corrective package — delivered (9 September 2026).** The first Part A
hypothesis is withdrawn. The End control is one button whose accessible name
flips on `authorityUncertain` (`trip-tracker.tsx:1167-1172`), `session` is seeded
`valid` (`:65`), and the failure aria tree shows that button enabled, so no
capability gate was involved. Investigation then found the frozen-End reload
affordance is **deliberate and test-covered** by `bc3c345`: three cases in
`trip-tracker.test.tsx` assert that a reload with a frozen End shows
`Reconcile trip`, re-submits the identical frozen manifest exactly once, never
re-freezes, never forgets evidence and never reopens capture. An attempt to
restore the `■ End trip` affordance broke exactly those three cases and was
reverted; `frontend/src` is byte-identical to `bc3c345`. The genuine defect is
therefore that `bc3c345` left the governed `r59-real-stack.spec.ts` inconsistent
with its own deliberate product change, and the correction is one line plus a
comment in that leased journey. R59's healthy window is ~6s against
`FLUSH_INTERVAL_MS` 15s and `FLUSH_AT_COUNT` 20, so **R59 does not evidence
healthy ping submission**; that property is covered by the component and
ping-queue tests only, and must not be read out of an R59 pass.

Backend item 14 was **reclassified from environmental to a security-relevant
product defect and fixed**: `release_contract.py` treated only a non-zero
`openssl` exit as failure, and `openssl x509 -checkhost` mismatch exit semantics
differ between the local OpenSSL 3.6.3 and ubuntu-latest's 3.0.x, so wrong-SAN
rejection did not fire on the deployment platform. The SAN is now checked
in-process against the certificate's DNS names, deliberately stricter than the
CLI it replaces: a certificate with no matching DNS SAN is refused rather than
falling back to the CN. Wildcard and IP-SAN handling were removed after review
as unreachable dead code that was looser than OpenSSL. Red/green proved by
emulating OpenSSL 3.0 exit semantics: pre-fix `DID NOT RAISE`, fixed raises;
455 module tests pass. This correction still owes the named specialist security
review that this repository requires for security checkpoints; it is recorded
here as an open obligation, not as a satisfied gate.

The eight `test_storage_csp_origin` cases were root-caused to a readiness loop
that caught only `(URLError, RemoteDisconnected)` while Linux docker-proxy
accepts-then-resets during Caddy boot, raising a bare `ConnectionResetError`. The
wait now covers every `OSError`, extends to 30s and fails loudly if the container
exited; every CSP assertion is byte-unchanged. Red/green proved by injecting the
reset: the pre-fix narrow catch raises the exact CI error, the fixed wait passes
all seven parametrisations. The two R13 budgets replaced raw `elapsed < 3.0` with
`_linear_scan_budget`, which times the identical code path on a smaller input of
the same shape in the same process and instrumentation; after review it uses two
references so neither payload size nor nesting depth can hide a regression behind
the other. Red/green proved: a genuinely quadratic redactor breaches both budgets
while the real one passes plainly and under `coverage run`. The backend job now
checks out full history so the predecessor rehearsal fails on capability rather
than on `unknown revision`, preserving C34's external limitation.

The consolidated independent review returned **FIX** and found two P1s that local
runs had missed: `ruff check .` failed on an `I001` import placement and a `B023`
loop-variable capture, either of which would have killed the backend job at lint
before pytest. Both are corrected and `ruff check .` passes. It also removed the
permissive SAN branches, narrowed the nested budget, and surfaced a missing guard
that a declared font face could be dropped from its exported chain and silently
fall back to a system font; that guard is added and mutation-proved.

Items 12-13 remain **explicitly unresolved**: both PostgreSQL cases pass in
isolation, with the backend env block including `F7_SEED_MAX_TRIPS_PER_DAY=1`, and
across both complete modules against real PostGIS 16-3.4. They are retained
unresolved rather than guessed, and the next exact-SHA run is the reproduction.
`test_r13_assignment_scan_is_linear_at_the_candidate_budget` still asserts a raw
`elapsed < 3.0` and is a known latent flake under coverage instrumentation; it is
recorded here so it is not re-diagnosed as environmental.

`.github/workflows/ci.yml` is an R59-leased file, so `R59_LEASED_FILES_DIGEST`
changes with this commit and any earlier R59 receipt is non-representative.

**Exact-SHA CI on `6f5d185` — 14 backend failures reduced to 2 (9 September
2026).** Run `34326905268` against the exact pushed SHA: quality **success**,
**R59 real-stack success** (the regression is closed), backend **failure** with
2 failed / 2753 passed in 1h16m, and changed-code coverage and real-stack e2e
**skipped** behind backend, so those two gates remain unevidenced. Fixed and
confirmed green in CI: all eight `test_storage_csp_origin` cases, the
predecessor-rehearsal revision resolution, the wrong-SAN TLS rejection, the R13
nested-assignment budget, and `test_r20_disbursement_postgresql`.

Two remain, both now evidenced rather than assumed:

`test_r13_malformed_structure_has_bounded_work_and_memory_before_candidates`
failed at 9.264s against a calibrated 1.109s. Local measurement shows
`redact_log_message` is **linear** on this input — 0.115us/char at 50k against
0.108us/char at 500k — so there is no super-linear redaction defect. The fault
was in the calibration itself: the reference was timed after `tracemalloc.stop()`
while the measured call ran inside the tracemalloc window, comparing an
uninstrumented run against an instrumented one. tracemalloc's per-allocation cost
is not a constant wall-clock factor, so the ratio inflated. The reference is now
timed inside the same tracemalloc window with `reset_peak()` between, leaving the
`peak < 8_000_000` assertion measuring only the full-size call. Red/green
re-proved after the change.

`test_postgres_nin_rewrap_and_trip_share_eligibility_before_profile_order` still
observes `DRIVER_PERSON_PAYEE_NOT_APPROVED` where it expects
`DRIVER_PROFILE_NOT_ACTIVE`. It is **not environmental and not a product
defect**: the test orchestrates a NIN rewrap against a concurrent trip start
through `acquire_work_eligibility_lock` and
`_acquire_work_eligibility_authority`, and the assertion depends on which
contender reaches work-eligibility first. The product refuses the trip in both
observed interleavings; only the cited unmet precondition differs. On the runner,
under coverage tracing and a different core count, the interleaving differs from
this machine, where the full 2755-case aggregate passes in 47m. The correct
correction is to make the intended interleaving deterministic rather than to
relax the assertion, and that has **not** been attempted here: it is retained as
the single open backend item, deliberately not patched by guesswork in a race
guard. Its sibling `test_r20_disbursement_postgresql` passed on this run without
any change, which is consistent with scheduling sensitivity rather than shared
state.

Repository status: locally accepted; **not CI accepted**; not release-ready; not
deployment-ready. C34 and the live device, provider, legal, staging and pilot
gates remain external. The TLS SAN correction still owes its named specialist
security review.

**Direct owner continuation — deterministic vehicle-approval race (9 September
2026, recorded before correction):** exact-SHA run `34335514041` against
`e408448cdfdff2aee9daa3de646a241e10758cb9` repeated the sole unresolved backend
failure: 2,754 tests passed and
`test_postgres_nin_rewrap_and_trip_share_eligibility_before_profile_order`
again observed `DRIVER_PERSON_PAYEE_NOT_APPROVED` instead of the intended
`DRIVER_PROFILE_NOT_ACTIVE` interleaving. Quality and R59 passed; changed-code
coverage and real-stack E2E were skipped behind backend. The owner authorizes
one Review-Required, test-only correction that makes the intended lock ordering
deterministic without relaxing either error, adding sleeps/retries, reducing
concurrency or weakening the product eligibility guard. It must reproduce under
coverage and runner-like scheduling, receive independent plan and post-build
review, and move `master` only by a verified normal fast-forward before a new
exact-SHA acceptance run. The nine protected provenance artifacts and all
external/release/deployment gates remain unchanged.

**Deterministic race correction — local evidence:** the test's prior event was
set only after the trip acquired the shared advisory lock, so the conditional
wait could not establish which transaction owned eligibility authority. On the
hosted runner, trip start read the initially active profile before waiting behind
the rewrap transaction; after serialization, its current person/payee query saw
the committed KYC reset and correctly refused work with
`DRIVER_PERSON_PAYEE_NOT_APPROVED`. Faster local scheduling let rewrap commit
before that initial read and produced `DRIVER_PROFILE_NOT_ACTIVE`. Both paths
failed closed, but the test asserted one without proving its ordering.

The corrected barrier now asserts rewrap already owns eligibility authority,
then holds it until trip start signals immediately before awaiting the same
lock. This proves genuine overlap and the exact identity-map/current-KYC ordering
without sleeps, retries, reduced concurrency, accepted-error sets or product-code
changes. With the barrier and old expectation, the focused real-PostGIS test
fails deterministically under coverage with the runner's person/payee result;
with the one exact expectation corrected, eight consecutive coverage runs pass.
The same source passes in a Linux Python 3.12.14 container constrained to two
CPUs and 3 GiB, and the complete vehicle-approval module plus adjacent KYC and
payee PostgreSQL concurrency checks pass 18 tests. `ruff check .`, progress
validation and diff checks pass. The independent Sol/medium plan review returned
REVISE; its truthful event rename, explicit rewrap-ownership assertion and
identity-map explanation are all incorporated. The separately named Sol/medium
TLS security specialist review returned PASS with no security finding, closing
that recorded review gate; its optional direct edge-case test matrix is a
non-blocking P3. The fresh Sol/medium consolidated post-build/minimal-change
review returned PASS with no finding over this correction, the complete
font/build amendment, every post-`bc3c345` correction, evidence truthfulness and
external gates. Exact-SHA CI remains due, so this is local correction evidence
only and no release or deployment status has changed.

**Additional exact-SHA concurrency evidence — correction authorized (9
September 2026, recorded before edit):** run `34344328340` targeted the exact
fast-forwarded SHA `a91ad26dd646faa7a8af62dddf3c050b29514ba6`. The corrected
vehicle-approval race passed; quality and R59 passed. Backend instead exposed
two different pre-existing harness races (2 failed / 2,753 passed), and coverage
and real-stack E2E were skipped. R08 proved through `pg_blocking_pids` that the
protected writer waited behind the disabling transaction and was then denied,
but asserted the order in which two coroutines appended labels after transaction
exit; that Python scheduling order is not database commit order. R20's provider
probe used `FOR UPDATE NOWAIT` while the losing concurrent claimant could still
legitimately hold the same row, so the probe itself raised and the production
failure boundary correctly moved the intent to `query_only`. Both tests pass in
focused local coverage runs, consistent with scheduler sensitivity rather than
an isolated product defect. The owner-authorized exact-SHA correction therefore
extends only to deterministic test barriers in
`tests/test_r08_admin_authorization_postgres.py` and
`tests/test_r20_disbursement_postgresql.py`: prove the committed disabled row
inside R08's denied writer transaction, and let R20's concurrent loser complete
before the provider-side committed-attempt/no-lock probe. Product code, database
locks, failure handling, concurrency, exact outcomes and all external gates stay
unchanged. Independent plan and post-build review, red/green evidence and a new
all-job exact-SHA run remain mandatory.

The independent concurrency plan review returned `REVISE`; its sole required
change was incorporated by bounding R20's coordinated pair with
`asyncio.wait_for(..., timeout=10)`. Run `34344328340` supplies pre-fix red
evidence for both scheduler-sensitive harness failures. After the correction,
five consecutive focused PostgreSQL coverage runs passed (2 tests each), both
changed modules passed together (8 tests), and the adjacent authorization and
disbursement group passed (21 tests). The two corrected races also pass under
the CI Python 3.12 runtime constrained to 2 CPUs and 3 GiB (2 tests). Full Ruff,
progress validation and diff whitespace checks pass. These are local correction
results only; consolidated post-build review and a new all-job exact-SHA run
remain due.

The independent Sol/high consolidated post-build review returned `PASS` with
no findings. It confirmed that R08 retains blocking, denial, persistence and
all 44 migrated call sites; R20 retains genuine concurrent claiming, exact
outcomes, one provider call, committed-attempt/no-lock proof, persistence and a
bounded hang guard; and the ledger truthfully keeps exact-SHA acceptance and all
external gates open. A new all-job exact-SHA run is the remaining acceptance
gate for this correction.

**CI-runtime coverage reconciliation — correction authorized (9 September
2026, recorded before policy edit):** exact-SHA run `34354263174` on
`41d006729a0aa1290a617060e8ea27b956ea4fc5` passed quality/build, the complete
backend suite and R59. Changed-code coverage then failed its exact global ratio
comparison and real-stack E2E was skipped. The downloaded successful backend
and frontend LCOV artifacts measure global 28,513 / 33,491 lines and 7,350 /
12,212 branches, while the committed receipt records 27,326 / 31,220 and 7,974
/ 12,212. No eligible product source changed between the receipt and candidate.
The receipt was generated from the local Python 3.14 evidence set, whereas the
authoritative CI/backend/runtime line is Python 3.12; Python 3.12 alone reports
2,269 covered class annotation-only lines that Python 3.14 largely omits, and
the interpreters also produce different covered branch counts. The owner-
authorized correction is limited to a reviewed, source-bound rebaseline using
the successful exact-SHA CI artifacts and explicit runtime provenance. It may
not change eligible source, coverage instrumentation or exclusions; lower the
D32 90% changed-line / 80% changed-branch floors; treat a skipped job as
evidence; or claim E2E, release or deployment acceptance. Independent plan and
post-build review, deterministic policy tests, provenance verification and a
new five-job exact-SHA run remain mandatory.

The independent Sol/high plan review returned `REVISE` twice and then `PASS`.
The incorporated findings require the producing backend job—not the consumer—to
emit an LCOV-hash, exact-SHA, CPython and coverage.py sidecar; protect that CI
wiring in the policy hash; make unprovenanced v1/v2-to-v3 reconciliation
single-use; and distinguish exact candidate-receipt admission from later
at-or-above-floor verification. GitHub's immutable job log independently records
CPython 3.12.14, coverage.py 7.16.0 and the generating commands; artifact API
metadata binds backend artifact `10109024797` and frontend artifact
`10105098738` to run `34354263174` and exact SHA `41d0067`, with archive and
extracted-LCOV hashes recorded in the fixed attestation. This supports one
reviewed migration without synthesizing producer evidence.

Red evidence: the two new runtime-reconciliation tests failed because the old
checker had no such authority or arguments. Green evidence: all 30 coverage-
policy tests pass, including tampered report rejection, v3 reuse rejection and
sidecar verification. The one-time receipt was generated under CPython 3.12.14
from the exact successful GitHub artifacts and separately re-admitted against
the candidate tree. It records global 28,513 / 33,491 lines and 7,350 / 12,212
branches, backend 25,266 / 28,514 and 4,616 / 6,770, frontend 3,247 / 4,977 and
2,734 / 5,442, plus the seven previously omitted font-family modules as
inventory additions. D32's changed-code floors remain exactly 90% line / 80%
branch; eligibility, instrumentation, exclusions and product source are
unchanged. Full static/document validation and consolidated post-build review
remain due before the normal fast-forward push; five-job exact-SHA acceptance
remains open.

The consolidated Sol/high post-build review initially returned `FIX` for an
unavailable consumer-side coverage.py import and ambiguous patch-version
authority. Both were removed: the checker now passes under sterile `python -S`,
producer coverage.py identity remains receipt-bound, and Python major/minor is
explicitly the measurement domain while the exact observed 3.12.14 remains in
legacy evidence. Re-review returned `PASS` with no findings after independently
rerunning all 30 policy tests, Ruff, diff checks and the receipt policy hash.
Exact-SHA CI remains the sole acceptance gate for this correction.

**Exact-SHA coverage-path stabilization — correction continued (9 September
2026).** Run `34371167803` against exact SHA
`5f84194df6e9527fcdcbc25b3cb66c9c58697d07` passed quality/build, all 2,757
backend tests, backend static verification and R59. The coverage job then
rejected the candidate receipt and real-stack E2E was skipped behind it. The
new backend artifact used the same CPython 3.12 / coverage.py 7.16 measurement
domain and unchanged eligible product source, but reported 25,229 / 28,514
backend lines and 4,596 / 6,770 branches, 37 lines and 20 branches below the
reviewed receipt. Comparing both LCOV artifacts and a real-PostgreSQL dynamic-
context reproduction mapped 29 missing lines and the dominant branch delta to
`test_postgres_end_upload_reconcile_and_grace_race_converges`: its six-way race
correctly permits the upload to serialize either as live evidence before End or
as quarantine evidence after sealing, so two passing runs traced different
valid paths. This is a test-evidence instability, not authorization to reduce
the D32/D33/D36 ratchet.

The owner's direct continuation authorizes the test-only correction under the
existing exact-SHA corrective package. Independent Sol/high plan review first
returned `REVISE`, rejecting any variance allowance and requiring proof that a
one-file correction covers the entire deficit; after that proof it returned
`PASS`. The existing test now commits one batch live that is included in the
eventual two-entry manifest, retains the original concurrent
End/End/upload/reconcile/grace/grace race for the second batch unchanged, then
proves after sealing that an exact retry returns the original live batch and an
altered same-key payload still conflicts. Product code, coverage policy,
baseline, thresholds, eligibility, instrumentation, exclusions and workflow
remain byte-unchanged.

Red evidence is run `34371167803`. In a disposable CPython 3.12.13 / coverage.py
7.16.0 container against real PostGIS, the final revised test passed four
consecutive runs. Each run kept the intentionally variable race but its union
with the failed-run LCOV added at least 38 lines and 22 branches, yielding a
conservative 28,514 global covered lines and 7,352 covered branches against the
committed 28,513 / 7,350 floors. The changed module passes 14 tests; the adjacent trip
group passes 57 with one local integration-gated skip; focused Ruff passes.
Consolidated post-build review and a new five-job exact-SHA run remain mandatory.
This is not CI, E2E, release or deployment acceptance; C34 and all live device,
provider, legal, staging and pilot gates remain open.

**Exact-SHA E2E selection correction — continued (9 September 2026).** Run
`34394676434` against exact SHA
`d64e5167ca2bfde999101f0bd51855393562af0c` passed quality/build, all backend
tests and static verification, R59, and changed-code coverage. The ordinary
real-stack E2E job then failed during Playwright collection because it also
collected `r59-real-stack.spec.ts`; that file imports its isolated stack helper,
which correctly refuses to run without `R59_PROJECT`. The dedicated R59 job had
already executed and passed the same journey through its governed wrapper.

The owner-authorized exact-SHA correction therefore adds only a mode-dependent
Playwright exclusion: ordinary desktop/mobile runs ignore the R59-only spec,
while `R59_REAL_STACK=1` retains it. A contract assertion failed before the
configuration change and passes afterward. Playwright discovery lists 134
ordinary tests in 20 files with no R59 journey, and separately lists exactly the
one R59 journey under `r59-chromium`. Product behavior, job dependencies,
coverage policy and all external gates remain unchanged. The independent
Terra/high consolidated post-build review returned `PASS` with no findings. A
new five-job exact-SHA run remains mandatory; this is not release or deployment
acceptance.

**Direct owner continuation — eliminate residual coverage variance (10
September 2026, recorded before implementation):** exact-SHA run `34410358441`
against `c56af25169c02bef4259ac4ccb8b79f03bf22617` passed quality/build, all
backend tests and static verification, and R59. Its backend artifact reported
25,264 / 28,514 lines and 4,616 / 6,770 branches; with the unchanged frontend
artifact this is two global lines below the committed 28,513-line floor, while
branches equal their floor. Changed-code coverage therefore failed and ordinary
real-stack E2E was skipped. The owner directly requests a correction. The
authorized scope is to identify the remaining schedule-sensitive coverage path
and add deterministic behavioral regression evidence without reducing the
baseline, changing eligibility/instrumentation, adding skips, or altering
product behavior. Independent plan and post-build review, repeated CI-runtime
evidence and a new five-job exact-SHA run remain mandatory. All external,
release and deployment gates remain unchanged.

The independent Sol/high plan review returned `REVISE` twice and then `PASS`.
The incorporated requirements make both regressions call the service directly
in one main event loop, assert exact error/status and persistence/audit
invariants, and require mutation-red plus at least four deterministic added
lines. A sentinel mutation to the early pending guard made its exact-code test
fail; bypassing the future-time comparison made the second test fail because no
exception was raised. Both mutations were restored, and the product service is
byte-identical to `c56af25`.

On CPython 3.12.14 with coverage.py 7.16.0, the two green tests passed three
consecutive runs. Their focused LCOV union with run `34410358441` adds 21
deterministic installation-evidence lines and 14 branches, projecting 25,285 /
28,514 backend lines and 4,630 / 6,770 backend branches; with the unchanged
frontend artifact, that is 28,532 global lines and 7,364 branches, respectively
19 and 14 above the committed floors. The complete installation-evidence,
R59-contract and changed-coverage-policy group passes 44 tests with one expected
local integration-gated skip; focused Ruff, progress validation and diff checks
pass. The independent Sol/high consolidated post-build review returned `PASS`
with no findings and independently confirmed the product-service hash and
coverage arithmetic. A fresh five-job exact-SHA run remains mandatory.

**Direct owner continuation — restore synthetic privacy authority in ordinary
real-stack E2E (10 September 2026, recorded before implementation):** exact-SHA
run `34509371010` against `98068d8e5609792eb7bd9e05722e85f0e678dc21` passed
quality/build, the complete backend suite and static verification, R59, and
changed-code coverage. Its ordinary real-stack E2E job executed but failed 35
desktop/mobile journeys after advertiser pages received
`503 PRIVACY_LIVE_USE_BLOCKED`; the stack was still configured as `local` with
synthetic disclosure mode absent even though it was populated only by the demo
seed. The owner directly requests the correction and authorizes continuation
without further permission prompts. The authorized scope is to mark only this
ordinary CI stack as `environment=test` with explicit synthetic disclosure
authority, preserve default/local and every production/live gate as fail-closed,
add a regression contract, run the real desktop/mobile workflow, obtain the
required independent plan and consolidated post-build reviews, and submit a
fresh five-job exact-SHA run. No legal approval, live authorization, skip,
coverage-policy, product-service, release, or deployment claim is authorized.

The correction now uses an API-only Compose override whose rendered ordinary
E2E environment is `test`, synthetic disclosure `true`, and live disclosure
`false`; the base stack remains `local`, live `false`, with synthetic disclosure
absent. Playwright selects exactly one fail-closed specialist mode (including an
explicit, externally hosted R14 edge probe) and ordinary discovery contains 57
tests in 16 generic files while excluding only the five specialist files.
State-changing cancellation and campaign-change journeys use unique disposable
campaigns, current assertions reflect accepted demo commercial terms, managed
creative uploads, governed measurement fail-closed states, and current driver
copy, and UUID quote references remove cross-project collisions. A fresh
CI-density stack exercised all 114 ordinary desktop/mobile cases serially with
94 passed, 20 pre-existing conditional skips and zero failures in 2.7 minutes;
69 focused Python contracts, frontend lint/typecheck, and 653 Vitest cases also
pass. A five-worker diagnostic exposed an existing PostgreSQL deadlock between
concurrent fraud/dispute writes; serial ordinary E2E prevents invalid shared-
stack test concurrency but does not claim to fix or concurrency-test that
product behavior. The required Sol/high revised plan review and independent
Sol/high consolidated post-build review both returned `PASS` with no findings;
the reviewer independently reproduced the focused contracts and discovery
matrix. A fresh five-job exact-SHA run remains pending.


## Canonical repository

`/Users/oluwasolaonigbinde/Projects/mobility-pkg01` on `feat/pkg-01`. The former
`mobility-master` directory was an obsolete Slice-0-only copy — never use it
to determine delivery status. When documentation conflicts, committed source
and Git history win.

## Delivered so far

| Stream | Status | Evidence |
| --- | --- | --- |
| Backend slices 0–13 (closed loop) | Complete | `docs/build-loop/slice-log.md`; closure commit `0dfb284` |
| Frontend F0–F6 (advertiser/driver/admin surfaces) | Complete as built demo/synthetic surfaces; the later RM4/RM5 PWA defects were closed by W0-F (D15/D16). Live authorization remains governed below. | Git `9189fe4`…`a5bcbb6`; `docs/archive/fablev1-work.md` journal |
| F7 auth/session hardening + audit + CI + backups | Complete, merged | Git `f40e0c4`…`236c2e4` (PR #1); architecture changelog v1.4 |
| Automated post-trip pipeline (arq worker) | Complete, merged | Git `159b0b1`, `4f69ef6`; architecture v1.5–v1.6 |
| S1 — payout engine v2 (hourly pay + daily caps, D2/D4/D9) | Complete, merged — RM1 fixed and the original whole-trip stationary grace retained for immutable payout-v2 history | Git `f9cd8ca`; architecture v1.8/v1.15, §16.1 [BUILT] |
| PKG-01 — foundations and empirical risk proof | Complete — RM2/RM6/RM7 closed; payout-v3 frozen parked-time behavior, PWA protocol/interrupted-flow build proof and provider-neutral release/recovery proof delivered; physical/live validation remains explicitly deferred | Git `d2cd424`…`be726a2` plus the package closure commit; architecture v1.30; D22/D23; automated/PostGIS/frontend/browser/recovery evidence |
| PKG-02 — money integrity and payout operations | Complete — RM8/RM10/RM11 closed; copied-route control, authoritative holds, clean release, encrypted payees, frozen provider instructions, line finality and carry-forward debt delivered provider-neutrally | Git through `e3a505e`; migrations `0022`–`0031`; architecture v1.37; Postgres/frontend/contract/synthetic end-to-end evidence and consolidated review resolved |
| PKG-06 / W3-03A–W3-04A — matching, offers, activity and public application | Complete checkpoints — advisory cars-only ranking, immutable expiring offers, reviewable activity flags and default-off non-enumerating pending driver applications; W3-04B/C are dependency-blocked | Package 6 commits through the W3-04A blocked-frontier checkpoint with selectively adopted Package 5 audit corrections; architecture v1.48–v1.52; focused PostgreSQL/Redis/backend/frontend/contract/live-journey evidence and consolidated reviews resolved |
| S4 — data lifecycle (ping partitions, retention purge, audit backfill, D10) | Complete, merged | Git `a879a3d`…`4f487e7`; architecture v1.9, §24.2 [BUILT] |
| W0-F — trip finality protocol + durable client queue (RM3/RM4/RM5, D15) | Complete — sealed-only money chain, post-seal quarantine, IndexedDB queue with stable retry keys; independently reviewed and hardened (D16: apply-after-initial-payout, pre-seal analytics recompute, fail-closed client) | Migrations `0016`+`0017`; architecture v1.16/v1.17; `tests/test_trip_seal.py`; live compose e2e |
| Pre-production ops (production Compose overlay, release smoke, backup/restore rehearsal) | Complete locally, **not deployed** | Git from `006d94e`; `docker-compose.production.yml`, `docs/runbook.md` |
| Current API contract | 31 migrations; controlled public baseline integration completed at PKG-02 closure | Payee/account, payout-batch, line-reconciliation, paid-balance and debt APIs are synchronized with the existing fraud/dispute/release contract across `docs/api/openapi.snapshot.json`, `openapi.json` and `schema.d.ts`. Later public endpoint/schema work must move all three artifacts together. |

**Nothing is deployed.** Staging/production remain research-only
(`docs/staging-options.md`) pending provider, budget, and operator approval
(Q32).

### Built does not mean live-authorized

Several useful interfaces predate the independent-review gates and may be used
only with demo/synthetic data until their owning checklist items land:

- Existing advertiser heatmaps/reports are **not live-authorized** under
  G-advertiser. W3-00D has supplied the safe build-time labels and methodology
  contract; W3-00C/E and W4-02A/B must still add disclosure control,
  reproducible measurement runs and governed issuance.
- PWA trip tracking and its durable queue are a tested protocol baseline, but
  **real-driver tracking is blocked** by G-GPS until RM2/RM9/RM15/RM18 close;
  W4-01 turns this surface into the D18 production screen-on pilot client.
- Payout rules, fraud review, release, encrypted payees, batch and reconciliation
  screens are provider-neutral synthetic foundations. The software G-money
  defects are closed, but **no real transfer is authorized** until
  `EXT-DISBURSEMENT-PROVIDER` supplies the approved provider and credentials.
- Current advertiser scheduling and driver activation flows are foundations,
  not the target commercial authority: G-commercial and W2-03A/D replace
  direct self-scheduling/activation before any live campaign.

## Where we are in the roadmap (architecture §31)

- **W0 — review remediation (new, 6 Aug 2026, D13):** **complete for PKG-01's
  built-code defects** — RM1
  fixed and RM2's renewable-grace half fixed 6 Aug 2026 (migration `0015`);
  **RM3/RM4/RM5 (trip seal protocol, stable retry keys, durable client queue)
  fixed 9 Aug 2026** (migration `0016`, D15, 465 tests green on PostGIS). It
  leads the remaining work. An independent code-verified review originally
  found seven defects in already-built code (architecture §35.1) plus eleven
  specification rows for unbuilt domains. RM1/RM3/RM4/RM5 are now closed,
  RM7 closed 16 Aug 2026 (PKG-01 FND-07, architecture v1.25); RM6 closed with
  payout-v3 revision/binding/correction authority, and RM2 closed under D22's
  acceptance-frozen rolling-displacement rule (architecture v1.30). Later
  tuning from real-route data creates a new revision and never rewrites history.
- **W1 — money correctness:** complete provider-neutrally. Worker, immutable
  payout history/corrections, data lifecycle, current fraud assessment and
  copied-route control, one hold predicate, clean/SLA release, encrypted payee
  versions, reconciled payout batches and carry-forward debt are built. Live
  transfer remains gated only by `EXT-DISBURSEMENT-PROVIDER`.
- **W2 — commercial layer:** not started. Billing/invoices (§15; W2-01A),
  file storage (§19), campaign/creative approval + installation evidence
  (§18), notification channels (§20).
- **W3 — reach:** not started. Retargeting at full Module G scope (§22),
  matching recommender + activity sweeps (§21), driver self-registration
  (§23).
- **W4 — production PWA + pilot readiness (D18):** not started. Installable
  screen-on PWA hardening/device proof, remaining CSV/PDF exports, Cardvert
  client-owned deployment, Abuja pilot and onboarding/training materials.

## Promise vs. delivery, by proposal module

| Proposal module | Built/demo-capable today (not necessarily live-authorized) | Outstanding / live-enablement owner |
| --- | --- | --- |
| A. Admin platform | Login/RBAC, user+org onboarding, drivers/vehicles, assignments, fraud review/disputes, payout rules/corrections, release SLA, payees, payout batches/reconciliation, traffic profiles and audit UI | Campaign/creative approval queues (W2), installation evidence (W2), retargeting monitoring (W3), exports (W4); live transfer provider input remains external |
| B. Advertiser dashboard | Campaigns CRUD, zones editor, analytics, demo heatmaps/reports/charts and payout-derived cost summaries | Company profile (W2-00D), creative *upload* (W2 — metadata-only today), billing/invoices (W2), governed approval/activation (W2), retargeting setup + insights, exposure score + high-exposure zone views (W3), disclosure-safe reports + CSV/PDF export (W4) |
| C. Driver app | Installable PWA: jobs, synthetic/demo trip tracking (idempotent ping batches), earnings + S1 trip breakdown, basic profile, durable offline ping queue + trip seal protocol (D15) | Offer accept/decline, self-registration, KYC and driver-owned vehicle lifecycle (W3); verified contact/notifications (W2); **production screen-on PWA/device proof** (W4). Native background app is Phase 2 |
| D. Analytics & impression engine | Route analytics, fraud flags, impression estimates, exposure/heatmap aggregation, payout eligibility classifier | Exposure score metric (`exposure_v1`) + high-exposure zone identification + retargeting insight capture (W3) |
| E. Dynamic driver payouts | Payout-v2/v3 immutable history, acceptance-frozen terms, maker-checker corrections, authoritative fraud holds, clean/SLA release, encrypted payees, frozen batches, line-level paid finality and carry-forward debt | Financially effective automated transfer remains disabled until `EXT-DISBURSEMENT-PROVIDER`; later KYC/provider approval lives in its owning packages |
| F. Heatmaps & reporting | Demo heatmap/route/report screens and daily metrics | Central disclosure/methodology/runs (W3), high-exposure zone + follow-up-targeting sections (W3), governed UI + CSV/PDF (W4); G-advertiser controls live use |
| G. Online-to-offline retargeting | — (privacy boundary designed, §22) | Entire module (W3): sources, segments, linkage, insights, controlled export and gated aggregate geography/time/context activation; identifiers/person-level payloads reject and live actions require legal/`EXT-AD-PLATFORM` inputs |

## Documentation authority

| Question | Source of truth |
| --- | --- |
| What the MVP must deliver | Direct client answers and approvals in `docs/decisions-log.md` D18–D20 override conflicting D11 proposal/default wording; the proposal remains scope context |
| How it is designed (current + target) | `docs/architecture.md` |
| Product decisions + Q1–Q34 statuses | `docs/decisions-log.md` (Part 1 history, Part 2 statuses) |
| What is authorised next and in what order | this file's package execution lock; checklist dependencies control internal checkpoints |
| What has been delivered so far | this file (control summary) → architecture changelog + Git/test evidence for detail |
| Client-readable product requirements and boundaries | `docs/product-requirements.md` (derived summary; decisions, architecture and this file win on conflict) |
| How to operate it | `docs/runbook.md` |
| Historical evidence | `docs/build-loop/` (closed backend ledger), `docs/archive/` |

## Update rules

1. A landed package updates this file in the same change: checklist evidence,
   package `DONE` status, ordered promotion/BLOCKED markings, both top control
   pointer/controller state, delivered-so-far row, wave position, and the
   module table. Exactly one package is active unless explicitly paused.
2. Client answers land in `decisions-log.md` first; if they change scope or
   design, `architecture.md` amends in the same commit — this file only
   records resulting *delivered* changes.
3. A future idea or owner request enters the relevant package/checklist before code is
   written. Only the project owner may intentionally reorder it; record why.
4. A package `DONE` claim requires every owned checklist item `DONE`, plus
   implementation, deterministic verification, a live
   simulation proportional to risk, required independent review, docs, and
   concrete evidence. Code alone is not completion.
5. `docs/next-steps.md` and `docs/build-loop/` may inform a plan but never
   authorise a package or override current architecture §35.
