# Ranked money-path findings

The packet does not provide the actual hourly rates, daily caps, campaign budgets, or confirmed receipts, so a numeric naira loss would be invented. I use:

* **R** = highest applicable hourly rate in NGN.
* **H** = applicable daily payable-hours cap.
* **A = 50 × H × R** = maximum one-day fleet earnings at the stated 50-vehicle ceiling.
* **W = 350 × H × R** = maximum seven-day fleet earnings.
* **L = 4,200 × H × R** = maximum 50-vehicle, 12-week pilot earnings.
* **F** = confirmed advertiser funds allocated to the affected campaign.

Where campaigns have different rates or caps, the precise amount is the sum of `rate × cap × active vehicle-days`.

Nothing is deployed. Payout v2, cap locking, recompute-day, ledger netting, and data retention are **[BUILT]**. Fraud holds, release scheduling, payout batching, billing, installation evidence, cancellation settlement, and bank reconciliation are **[TARGET]**. Findings against target components are corrections required before those slices land, not claims about a current implementation exploit.

| Rank | ID | Design path                                                                                                                           | Boundary                                                 | Classification                              | Maximum plausible pilot consequence                                                                                                        |
| ---: | -- | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
|    1 | G1 | A single generic admin can retroactively manufacture earnings and approve their path toward disbursement                              | Recompute **[BUILT]**; release/batch **[TARGET]**        | **CONFIRMED DESIGN GAP**                    | No finite design-level NGN ceiling; up to adjustments over all 4,200 vehicle-days, practically bounded by available cash                   |
|    2 | G2 | GPS proves movement of a driver-controlled phone, not movement of the approved branded vehicle                                        | Tracking/payout **[BUILT]**; evidence/holds **[TARGET]** | **CONFIRMED DESIGN GAP**                    | Up to **L** if systematic across the pilot                                                                                                 |
|    3 | G3 | Manual payout runs can be duplicated, partially replayed, or redirected because reservation and bank reconciliation are not specified | S3 **[TARGET]**                                          | **CONFIRMED DESIGN GAP**                    | Up to **W** per duplicated full batch; up to **L** if repeated                                                                             |
|    4 | G4 | Fraud review is fail-open because release relies on the absence of an `open` flag rather than a durable, completed fraud decision     | S2/S3 **[TARGET]**                                       | **CONFIRMED DESIGN GAP**                    | Up to **W** per release cycle; up to **L** if systematic                                                                                   |
|    5 | G5 | No invariant connects confirmed campaign funding to the maximum driver liability created by assignments, caps, and scope changes      | W2/W3 **[TARGET]**                                       | **CONFIRMED DESIGN GAP**                    | Up to `max(0, L − F)`                                                                                                                      |
|    6 | G6 | One incoming bank receipt can be fabricated, replayed, misallocated, or later reversed without withdrawing campaign authority         | W2 **[TARGET]**                                          | **CONFIRMED DESIGN GAP**                    | Driver liability of falsely funded campaigns, up to **L**                                                                                  |
|    7 | G7 | Cancellation lacks an immutable financial cutoff and a defined settlement equation                                                    | W2 **[TARGET]**                                          | **CONFIRMED DESIGN GAP**                    | Up to the affected campaign’s confirmed receipts plus approximately **A** of post-cutoff/in-flight earnings                                |
|    8 | H1 | Client-controlled GPS timestamps may be stretchable or shiftable into payable periods                                                 | Ingestion/payout **[BUILT]**                             | **HYPOTHESIS REQUIRING CODE/TEST EVIDENCE** | Up to **L** if timestamp validation is absent                                                                                              |
|    9 | H2 | Assignment and trip exclusivity may be vulnerable to check-then-insert races or overlapping sessions                                  | Assignment/trips **[BUILT/TARGET]**                      | **HYPOTHESIS REQUIRING CODE/TEST EVIDENCE** | One additional campaign-cap layer, potentially up to **L**                                                                                 |
|   10 | H3 | Stationary-grace reset behavior may allow stop–nudge–stop time farming                                                                | Eligibility **[BUILT]**                                  | **HYPOTHESIS REQUIRING CODE/TEST EVIDENCE** | Up to the full cap for affected drivers; **L** if systemic                                                                                 |
|   11 | G8 | Assigning an entire cross-midnight trip to its start day violates the Lagos-calendar-day cap                                          | Payout v2 **[BUILT]**                                    | **CONFIRMED DESIGN GAP**                    | Up to **A** misallocated on an affected calendar day; usually a shift between days rather than an increase over the whole campaign ceiling |

---

## G1 — Single-admin retroactive repricing and self-approval

1. **Attacker and objective.** A malicious or compromised admin, potentially colluding with a driver, wants to create additional payable earnings for historical trips and move them into a payout.

2. **Exact preconditions.**

   * The driver already has calculated trips whose ledger entries are `available`, or old enough to become available immediately.
   * The admin can edit the governing payout rule and invoke `recompute-day`.
   * No immutable payout-rule version is bound to the accepted offer or original trip.
   * No second person must approve a positive retroactive correction.
   * When S3 is built, the same generic `admin` role can generate and complete payout runs.

3. **Step-by-step attack sequence.**

   1. Select one or more historical days for a colluding driver.
   2. Temporarily raise `hourly_rate_naira`, the daily cap, or permissive eligibility parameters on the governing rule.
   3. Invoke `POST /admin/payouts/recompute-day`.
   4. The documented policy reprices the day using the rule’s **current terms** and posts positive append-only adjustments.
   5. Restore the rule to its original values.
   6. Because differential entries inherit the corrected trip’s status and old trip timing, an adjustment against an `available` trip is immediately available rather than receiving a new seven-day review period.
   7. The same admin resolves any blocking fraud state and includes the adjustment in a payout run.

4. **References.** `02-architecture.md` §§6.3, 16.1, 16.2, 16.3 and 17; `03-client-decisions.md` D5, D9(f–g), Q21 and Q22; `04-delivery-status.md` S1 **[BUILT]**, S2/S3 outstanding.

5. **Documented control intended to prevent it.** Payout calculations are write-once; drift returns 409; corrections are append-only; recompute-day is audited; formula/currency mixtures are refused; only named admins are supposed to adjust earnings.

6. **Why the control fails.** The controls preserve evidence but do not constrain authority. D9 intentionally makes current terms authoritative for rate-correction true-ups, but the architecture has no immutable correction authorization, no effective-dated rule versions, no maximum approved delta, and no maker-checker step. The current role model has only `admin`, not an enforceable “named payout adjuster” capability. Audit detects the transfer after the obligation has been created; it does not stop it.

7. **Maximum plausible financial consequence.** For `n` affected vehicle-days, the unauthorized differential can approach:

   `n × H_new × R_new − existing net earnings`

   with `n ≤ 4,200` at pilot scale. Because no business ceiling on `R_new` or `H_new` is stated, the architecture provides no finite NGN maximum. The practical limit is available cash and whatever bank authorization ops permits.

8. **Smallest credible correction.**

   * Keep D9’s rate-correction feature, but make payout rules immutable and effective-dated.
   * Bind each accepted offer and trip to a specific rule version.
   * Make a retroactive correction an explicit `correction_order` containing the affected date, approved terms, reason, projected total delta, creator, and separate approver.
   * Prevent the creator from approving the same positive correction.
   * Post positive correction entries as `pending` with their own release date; negative reversals may reduce available balances immediately.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before pilot launch`.

---

## G2 — Plausible phone movement can be paid even when the approved branded vehicle did not move

1. **Attacker and objective.** A driver wants the capped hourly payment without actually operating the approved, branded vehicle.

2. **Exact preconditions.**

   * The driver has an active assignment.
   * Installation evidence has been approved once.
   * The driver controls the phone and authenticated tracking client.
   * The phone can travel in another vehicle, or can produce a sufficiently plausible synthetic trace.

3. **Step-by-step attack sequence.**

   1. Complete installation and obtain approval using a valid photo.
   2. Remove the branding, leave the approved vehicle parked, or simply leave that vehicle unused.
   3. Carry the tracking phone in another moving vehicle, give it to another person, or submit a plausible synthetic route.
   4. Start a trip and produce pings that remain in the target area and time window, report acceptable accuracy, show plausible speed, and avoid teleport/gap thresholds.
   5. End the trip.
   6. The classifier observes valid phone movement and computes gross hourly earnings.
   7. If no heuristic flag is raised, the driver ultimately receives the payment even though the advertiser’s approved vehicle did not provide the exposure.

4. **References.** `01-mvp-requirements.md` §§3.C–3.E and Month 3/Month 4 deliverables; `02-architecture.md` §§8.6, 16.1, 17, 18, 19.3 and 21; `03-client-decisions.md` D2, D4, D5, D9, Q5 and Q17; `04-delivery-status.md` shows PWA/payout **[BUILT]** and installation evidence/fraud review outstanding.

5. **Documented control intended to prevent it.** Screen-on trip tracking, target-zone and time-window checks, movement classification, GPS-gap/accuracy/teleport checks, stationary grace, fraud flags, one-time installation evidence, daily caps, and hold-and-review.

6. **Why the control fails.** Those controls establish that a driver-controlled device produced a plausible movement trace. They do not establish that the phone was inside the assigned vehicle, that the approved creative remained installed, or that the vehicle whose registration was approved performed the trip. A real trip in a different vehicle defeats even perfectly implemented speed and GPS-plausibility checks.

7. **Maximum plausible financial consequence.** One driver can receive up to `84 × H × R` over a 12-week pilot. If the weakness is systematic across the 50-vehicle ceiling, the exposure is **L**. Once transferred, later fraud confirmation only creates a negative balance; the architecture expressly does not claw cash back automatically.

8. **Smallest credible correction.** At pilot scale, use compensating controls rather than redesigning GPS:

   * Bind each assignment to one approved app installation/device and one vehicle.
   * Require a server-nonce, start-of-shift proof-of-display while the vehicle is stationary.
   * Use randomized physical spot checks and periodic evidence renewal for high earners.
   * Detect identical/copy-shifted routes across vehicles, accounts, and days.
   * Hold the affected day if a proof challenge is missed or another device/session is active.
   * Native attestation in W4 can add signal quality, but it must not be treated as proof that the advertised vehicle moved.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before pilot launch`.

---

## G3 — Manual payout runs can be duplicated, partially replayed, or redirected

1. **Attacker and objective.** A driver benefiting from an operational retry, a malicious admin, or an outsider who alters an exported payout file wants the same earnings transferred twice or transferred to a substituted account.

2. **Exact preconditions.**

   * Ledger entries are `available`.
   * S3 follows the documented manual flow: generate run, export, make bank transfers, then mark entries `paid`.
   * The design has no stated `batched/reserved` state, unique active batch membership, immutable beneficiary snapshot, or per-line bank reconciliation.

3. **Step-by-step attack sequence.**

   1. An admin generates and exports a weekly payout run.
   2. The bank executes all or part of the file.
   3. The browser, workstation, or admin process fails before the platform marks the entries paid.
   4. The entries still appear available.
   5. A retry or second admin generates another run containing the same entries.
   6. The bank executes the second file, paying successful lines again.
   7. In a redirect variant, a beneficiary account is changed after batch creation, or the downloaded file is edited before upload; the system has no documented immutable account snapshot or file hash to reconcile against.
   8. In a partial-success variant, rerunning the whole file to pay failed lines duplicates the lines that succeeded.

4. **References.** `01-mvp-requirements.md` §3.E and Month 4 payout operations; `02-architecture.md` §§14.3, 16.2 and 16.3; P6 and P9; `03-client-decisions.md` Q22, Q26 and Q27; `04-delivery-status.md` W1-S3 outstanding.

5. **Documented control intended to prevent it.** A `payout_batches` table, line items referencing ledger entries, transfer references, an eventual `paid` status, audit records, and the general rule that jobs and retry-prone writes be idempotent.

6. **Why the control fails.** Section 16.3 does not instantiate those general idempotency rules. It does not require:

   * one active/completed batch line per ledger entry;
   * an atomic claim before export;
   * an idempotency key for run creation;
   * per-line submitted/succeeded/failed/returned states;
   * a versioned bank-account snapshot;
   * unique external transfer references; or
   * reconciliation of bank results before `paid`.

   The irreversible bank step therefore sits between two database states without a recovery protocol.

7. **Maximum plausible financial consequence.** One duplicated full weekly run is up to **W**. Repeating the failure across the pilot can reach **L**. Redirecting a full file also exposes up to **W** in one incident.

8. **Smallest credible correction.**

   * Use `draft → reserved → exported → submitted → reconciled/completed | cancelled`.
   * Atomically reserve entries and enforce one non-cancelled batch line per ledger entry with a database constraint.
   * Calculate each payee line from the **net** available balance, including reversals.
   * Snapshot the exact verified bank-account version, beneficiary name, amount, and line ID.
   * Hash the exported file and invalidate it if any line or beneficiary changes.
   * Reconcile bank results line by line using a unique bank transaction reference.
   * Mark an entry `paid` only when its specific line is reconciled as successful; failed or returned lines remain separately retryable.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before the dependent slice`.

---

## G4 — Acknowledging a fraud flag can remove the hold before review is complete

1. **Attacker and objective.** A flagged driver, potentially aided by a colluding or social-engineered admin, wants pending flagged earnings released before the fraud case is resolved.

2. **Exact preconditions.**

   * A serious flag is `open`.
   * The corresponding ledger entry is pending and near its release date.
   * S2 implements the documented lifecycle: `acknowledged` means under review.
   * S3 implements the documented release predicate using “no open fraud flags/holds.”

3. **Step-by-step attack sequence.**

   1. A suspicious trip creates an `open` flag and pending earnings.
   2. Shortly before the release sweep, an admin legitimately acknowledges the flag to begin review.
   3. Its status changes from `open` to `acknowledged`.
   4. Because the hold is described as a predicate over `open` flags, the trip now has no `open` flag.
   5. The release sweep moves the ledger entry to `available`.
   6. A payout run transfers it before the admin chooses `dismissed` or `confirmed`.

   A second path exists when fraud detection fails or is stale: there is no positive “fraud screening completed and current” record, so absence of a flag can also look identical to a clean result.

4. **References.** `02-architecture.md` §§14.2, 16.2 and 17; `03-client-decisions.md` D5, D9(e–g), Q21 and Q22; `04-delivery-status.md` identifies S2 fraud review and S3 release as outstanding.

5. **Documented control intended to prevent it.** Fraud runs before payout in the trip pipeline; serious `open` flags hold pending entries; acknowledged flags are reviewed by admins; earnings wait seven days; post-release flags produce reversal recommendations.

6. **Why the control fails.** “Under review” and “held” are not the same durable state. The lifecycle transition required to perform a review removes the status named by the release predicate. The architecture also treats absence of a flag as sufficient rather than requiring a current successful fraud assessment, and it does not specify serialization between flag creation/resolution and release.

7. **Maximum plausible financial consequence.** Up to all flagged earnings included in a weekly sweep, bounded by **W**. If every suspicious trip is acknowledged before release or the detector is unavailable, the systematic ceiling is **L**.

8. **Smallest credible correction.**

   * Record a current fraud assessment on each trip: `pending | clean | flagged | error`, with fraud version and input fingerprint.
   * Release only when the assessment is current and successful.
   * Derive `hold_active` as true for `open`, `acknowledged`, and unresolved `confirmed` cases; only `dismissed` releases the hold.
   * Use the same per-trip advisory lock, or equivalent row-lock protocol, in fraud-state changes and release.
   * Recheck the condition inside the transaction that changes the ledger status.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before the dependent slice`.

---

## G5 — Paid invoice status does not bound the campaign’s driver liability

1. **Attacker and objective.** An advertiser wants additional vehicle exposure without providing the additional funds required to pay drivers. The same path can arise from an honest quotation or configuration mistake.

2. **Exact preconditions.**

   * An initial invoice is paid and the campaign becomes active.
   * Campaign scope can expand through dates, vehicles, or other financially additive changes.
   * Driver payout terms and assignments can create liability greater than the original funded amount.
   * No persisted funded driver-liability ceiling or reservation exists.

3. **Step-by-step attack sequence.**

   1. The advertiser funds a legitimate initial campaign scope.
   2. The campaign passes the activation funding gate.
   3. The advertiser requests an expansion that applies immediately under Q9, or additional assignments are added.
   4. Drivers accept offers and perform eligible hours under D2/D4.
   5. The ledger creates enforceable driver liabilities.
   6. The incremental invoice or funding is delayed, disputed, or never paid.
   7. The platform must either pay drivers from its own funds or breach its driver obligation.

4. **References.** `01-mvp-requirements.md` §§3.B, 3.E and 6.E; `02-architecture.md` §§15.2, 15.5, 16.1, 18 and 21; `03-client-decisions.md` D2, D4, D12, Q2, Q9 and Q15.

5. **Documented control intended to prevent it.** Balance before activation, invoice-derived funding status, daily driver caps, a worker budget sweep, and admin final activation.

6. **Why the control fails.** These controls protect different quantities:

   * Invoice status says that some invoiced advertiser price was paid.
   * Section 15.5 explicitly says advertiser “spend” is not the same as driver payout cost.
   * D4 caps each driver per day but does not cap total campaign liability.
   * Q9 allows immediate expansions.
   * Nothing reserves maximum driver liability when an offer, assignment, or expansion becomes effective.

   Consequently, a fully “funded” campaign can still create unfunded driver obligations.

7. **Maximum plausible financial consequence.** `max(0, total authorized driver liability − confirmed funding or expressly approved platform subsidy)`. Without a liability authorization, the pilot ceiling is approximately `max(0, L − F)`.

8. **Smallest credible correction.**

   * Add an immutable campaign financial authorization containing the funded advertiser amount, any separately approved platform subsidy/credit, and a maximum driver-liability amount.
   * At offer/assignment activation, reserve `rate × cap × covered vehicle-days`.
   * Allow Q9 expansions to apply immediately only inside pre-funded headroom; otherwise they remain `pending_funding`.
   * Prevent new sessions before the reserve is exceeded, while still paying hours already validly authorized and performed.
   * Keep this liability reserve separate from advertiser budget/spend reporting.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before the dependent slice`.

---

## G6 — One incoming receipt can fund more than one obligation

1. **Attacker and objective.** An advertiser, with a careless or colluding admin, wants one bank transfer to activate multiple campaigns or to appear larger than it was.

2. **Exact preconditions.**

   * Manual transfers are recorded by an admin.
   * `payments` has a provider/reference field, but no documented uniqueness or reconciliation invariant.
   * Invoice paid status is the sum of confirmed payment rows.
   * Activation trusts invoice status.

3. **Step-by-step attack sequence.**

   1. The advertiser sends one legitimate bank transfer or supplies convincing evidence of one.
   2. The transfer is entered twice against the same invoice, or once against each of two invoices.
   3. Alternatively, a browser retry records the same transfer again because the record-payment write has no stated idempotency key.
   4. Each invoice derives a paid or sufficiently funded status from the duplicate rows.
   5. One or more campaigns activate.
   6. Drivers accrue earnings.
   7. Later bank-statement reconciliation discovers that only one receipt—or no receipt—existed.

   The gateway version has a related weakness: uniqueness of a webhook **event ID** does not establish uniqueness of the underlying provider transaction if a provider emits multiple event IDs for the same transaction/status history.

4. **References.** `02-architecture.md` §§15.2–15.4 and 18; `03-client-decisions.md` Q2, Q3 and Q15; P6 and P9.

5. **Documented control intended to prevent it.** Admin confirmation and audit for manual payments; provider signature verification and unique event IDs for gateway callbacks; invoice status derived from confirmed payments.

6. **Why the control fails.** The architecture does not require a canonical external cash-receipt identity, exact invoice-currency matching, amount matching, a separate bank-reconciled state, or uniqueness of the provider transaction reference. A duplicated payment row is therefore a second funding fact even when there was only one external receipt. The design also does not say that a corrected/reversed receipt continuously withdraws campaign funding authority.

7. **Maximum plausible financial consequence.** The driver liability created by all falsely activated scope, up to **L** at the stated pilot ceiling.

8. **Smallest credible correction.**

   * Represent one external receipt once, with unique bank/provider transaction ID, amount, currency, payer, received date, and immutable source evidence.
   * If one receipt is allocated across invoices, use separate allocation rows rather than duplicating the receipt.
   * Use `observed → reconciled → confirmed | rejected/reversed`; activation counts only reconciled/confirmed allocations.
   * Require exact currency matching and verify provider amount/reference before confirmation.
   * A receipt reversal or correction must immediately recompute funding status and pause further earning authority at a recorded cutoff.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before the dependent slice`.

---

## G7 — Cancellation can produce both post-cutoff earnings and an excessive refund

1. **Attacker and objective.** A colluding advertiser and driver want the advertiser to receive the contractual refund while the driver continues to generate paid time after cancellation. A mistaken admin can cause the same loss.

2. **Exact preconditions.**

   * A paid campaign has one or more active trips.
   * Cancellation occurs while clients may be offline or holding unsent batches.
   * The payout classifier has no documented immutable cancellation cutoff.
   * The settlement record has no specified schema or amount invariant.

3. **Step-by-step attack sequence.**

   1. A driver starts a valid trip.
   2. The advertiser cancels the campaign.
   3. Campaign and assignment statuses change, but the trip continues on an offline or non-refreshed client.
   4. The driver uploads the remaining pings and ends the trip.
   5. Payout v2 evaluates GPS movement, campaign time windows, and zones; the architecture does not require it to clip intervals at the cancellation event.
   6. The driver receives post-cancellation earnings.
   7. Separately, the admin settles a refund outside the platform.
   8. Because §15 defines no settlement equation, unique settlement revision, or refund transaction reconciliation, the admin may refund the full receipt without accounting for contractual charges or accrued driver liability, or may record/pay the settlement twice.

4. **References.** `01-mvp-requirements.md` §6.B cancellation/refund rules; `02-architecture.md` §§15, 16.1, 18, 21 and §30’s cancellation/refund placement row; `03-client-decisions.md` Q9 and Q24.

5. **Documented control intended to prevent it.** Q24 says assignments and earnings stop immediately, drivers are paid only to that moment, refunds occur outside the platform under the contract, and a terminal financial-settlement record is stored.

6. **Why the control fails.** The stated business rule has no event-time implementation shape. There is no `financial_cutoff_at` that all ingestion, classification, recompute, release, and settlement paths must use. The billing data model also contains no cancellation-settlement entity, contractual calculation inputs, one-current-settlement constraint, or external refund-reference uniqueness.

7. **Maximum plausible financial consequence.** Up to the contractual refund—potentially the campaign’s confirmed receipts—plus post-cutoff earnings. With immediate status propagation but one in-flight day of exposure, the latter is bounded roughly by **A**. Duplicate external refunds could add another refund amount if bank operations do not catch them.

8. **Smallest credible correction.**

   * In the cancellation transaction, set an immutable `financial_cutoff_at`, deactivate assignments, and record the cancellation version/reason.
   * Accept late pings as evidence if necessary, but clip payable intervals at that cutoff in normal calculation and recompute.
   * Finalize all pre-cutoff liabilities before approving settlement.
   * Store append-only settlement revisions containing confirmed receipts, contractual basis, accrued driver liability, non-refundable charges, approved refundable amount, approvers, and unique external refund reference.
   * Only the approved current settlement may be reconciled as paid.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before the dependent slice`.

---

## H1 — Client timestamps may allow payable-time stretching or window shifting

1. **Attacker and objective.** A driver wants to make a short or out-of-window movement appear to cover more payable time or an allowed campaign window.

2. **Exact preconditions.**

   * The API accepts client-provided `recorded_at`.
   * The implementation does not strongly bind it to server-observed trip start/end, batch receipt time, monotonic order, and bounded clock skew.
   * Eligibility calculations use those client times to construct intervals.

3. **Step-by-step attack sequence.**

   1. Start an authenticated trip.
   2. Generate a plausible route.
   3. Assign timestamps that are stretched, shifted into an allowed window, or arranged to avoid a GPS-gap classification.
   4. Upload through the offline/retry flow.
   5. End the trip.
   6. If eligibility trusts the client timeline, the intervals are classified and priced as payable.

4. **References.** `02-architecture.md` §§7.1, 8.6, 16.1 and 24.2; `03-client-decisions.md` D9, Q5 and Q10.

5. **Documented control intended to prevent it.** Explicit trip Start/End, GPS-gap and teleport checks, integer interval accounting, input fingerprints, and DB-clock use by jobs.

6. **Why success or failure cannot be determined from the documents.** The architecture states that `recorded_at` is stored and used for partitioning, but does not state the accepted skew, monotonicity requirements, relation to `received_at`, whether trip start/end are server timestamps, or which clock determines payable interval duration. Offline sync makes this distinction material.

7. **Maximum plausible financial consequence.** Up to `H × R` per driver-day and **L** if the same weakness is exploitable across all pilot accounts.

8. **Smallest credible correction.**

   * Store both capture time and server receipt time.
   * Require monotonic captured times within immutable server trip boundaries.
   * Reject future points and unreasonably old/backdated points.
   * Bound every payable interval by both client delta and the authenticated server-session envelope.
   * Test compressed, stretched, reordered, future, duplicated, and delayed traces.

9. **Classification.** `HYPOTHESIS REQUIRING CODE/TEST EVIDENCE`.

10. **Required timing.** `before pilot launch`.

---

## H2 — Assignment and trip exclusivity may not survive concurrency

1. **Attacker and objective.** A driver or malicious admin wants one vehicle or one physical drive to generate earnings under multiple campaigns.

2. **Exact preconditions.**

   * The service checks “one campaign per vehicle” before insertion but does not take a vehicle lock or rely on a database exclusion/unique constraint.
   * The trip service does not enforce one unended trip per driver and vehicle.
   * Cross-trip route reuse is not detected.

3. **Step-by-step attack sequence.**

   1. Submit two concurrent assignment-creation requests for the same vehicle.
   2. Both transactions read that the vehicle has no conflicting campaign.
   3. Both create offers/assignments.
   4. The driver accepts and activates both.
   5. Start overlapping trips, or submit the same physical route under each assignment.
   6. Each campaign has an independent D4 cap, so each creates a separate payable calculation.

4. **References.** `02-architecture.md` §§6.4.6, 8.6 and 21; `03-client-decisions.md` Q8 and Q16.

5. **Documented control intended to prevent it.** The one-campaign-per-vehicle rule is placed in `create_assignment`; ping batches are idempotent within a trip; assignments require driver acceptance.

6. **Why verification requires code or tests.** Section 21 says the rule lives in the service layer but does not say whether that service takes a transaction lock or has a database backstop. The architecture also does not state a unique active-trip constraint. Existing code could contain protections that the document omits.

7. **Maximum plausible financial consequence.** Each extra campaign/session can create another `H × R` per vehicle-day. One duplicate layer across the pilot could approach **L**, plus advertiser refund exposure where only one creative was actually displayed.

8. **Smallest credible correction.**

   * Add a database partial unique or exclusion constraint for conflicting active assignment statuses per vehicle.
   * Take a transaction-scoped vehicle advisory lock during assignment creation/activation.
   * Add partial unique constraints for one unended trip per driver and per vehicle.
   * Reject overlapping historical trip intervals unless explicitly reviewed.
   * Detect identical or time-shifted ping payloads across trips/accounts.

9. **Classification.** `HYPOTHESIS REQUIRING CODE/TEST EVIDENCE`.

10. **Required timing.** `before pilot launch`.

---

## H3 — Stationary grace may be reset repeatedly to farm the cap

1. **Attacker and objective.** A driver wants to remain mostly parked while repeatedly resetting the stationary grace period so that most of the session remains eligible.

2. **Exact preconditions.**

   * Grace is restarted after any interval classified as moving.
   * The movement threshold can be crossed by a small displacement, GPS jitter, or a short loop.
   * Fraud rules do not independently detect the repeating stop–nudge–stop pattern.

3. **Step-by-step attack sequence.**

   1. Start a trip inside an approved area and campaign window.
   2. Remain stationary for slightly less than the grace duration.
   3. Move just far or fast enough to be classified as moving.
   4. Stop again, obtaining a fresh grace period.
   5. Repeat until reaching the daily cap.
   6. Receive payment for a session containing very little meaningful vehicle operation.

4. **References.** `02-architecture.md` §§16.1, 17 and 32 R1; `01-mvp-requirements.md` §§3.C–3.E; `03-client-decisions.md` D2, D4, D5 and Q5.

5. **Documented control intended to prevent it.** The classifier has `stationary(+grace)` exclusions, movement thresholds, GPS hygiene, daily caps, and a separate fraud/anomaly engine.

6. **Why verification requires code or tests.** The documents do not define whether grace is per stationary episode, cumulative per trip/day, or reset only after sustained displacement. They also do not give the movement hysteresis or fraud-pattern interaction.

7. **Maximum plausible financial consequence.** Up to the full `H × R` per affected driver-day and **L** if every driver can use the pattern.

8. **Smallest credible correction.**

   * Make grace a cumulative session/day allowance rather than an endlessly renewable allowance.
   * Require sustained displacement over a rolling time/distance window before resetting stationary state.
   * Use hysteresis between moving and stationary thresholds.
   * Add synthetic property tests for repeated short movements, GPS jitter, traffic jams, and tight loops.
   * Monitor grace-paid versus verified-moving time per driver during the pilot.

9. **Classification.** `HYPOTHESIS REQUIRING CODE/TEST EVIDENCE`.

10. **Required timing.** `before pilot launch`.

---

## G8 — A cross-midnight trip can consume the wrong day’s cap

1. **Attacker and objective.** A driver wants to use otherwise unused cap from one day for hours physically driven on the next day, then also consume the next day’s cap.

2. **Exact preconditions.**

   * A trip can span Lagos midnight.
   * The prior start day has remaining cap.
   * The following day also permits eligible driving.

3. **Step-by-step attack sequence.**

   1. Start a trip shortly before midnight on day N.
   2. Perform up to H eligible hours after midnight.
   3. The complete trip is allocated to day N because the architecture keys the cap to the trip’s start day.
   4. Later on day N+1, start another trip and consume day N+1’s full cap.
   5. The driver receives up to 2H for hours physically occurring on day N+1.

4. **References.** `02-architecture.md` §16.1, especially the advisory-lock key and day-boundary rule; `03-client-decisions.md` D4, D9 and Q5.

5. **Documented control intended to prevent it.** An advisory lock on `(driver, campaign, Lagos-day)` and aggregation of all trips charged to that key.

6. **Why the control fails.** The lock works correctly for the key it is given, but the key is semantically wrong for a trip crossing midnight. D4 is a Lagos-calendar-day cap, not a trip-start-day cap.

7. **Maximum plausible financial consequence.** Up to `H × R` extra relative to the correct rule for one driver on the affected calendar day, or **A** across 50 vehicles. Over the entire campaign this often shifts capacity between adjacent days rather than exceeding the total `cap × campaign-days` quotation; the real loss occurs where the prior day’s cap would otherwise have been unusable because of schedule, start-date, or operating-window restrictions.

8. **Smallest credible correction.** Split the eligibility timeline at every Africa/Lagos midnight, allocate payable seconds to each touched day, and acquire all affected day locks in deterministic order. Store the per-day allocation with the calculation so recompute-day can reproduce it.

9. **Classification.** `CONFIRMED DESIGN GAP`.

10. **Required timing.** `before pilot launch`.

---

## Checked scenarios prevented by the documented design

| Scenario checked                                                     | Why it is prevented                                                                                               | Classification                                                                                     | Timing                       |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------- |
| Retry the exact same ping batch to double count it                   | Unique `(trip_session_id, idempotency_key)` and replay returns the recorded batch                                 | `PREVENTED BY THE DOCUMENTED DESIGN`                                                               | `monitor during the pilot`   |
| Two workers calculate and ledger the same trip twice                 | Write-once calculation, one-trip-payout uniqueness, named-constraint convergence, fingerprints, and ledger repair | `PREVENTED BY THE DOCUMENTED DESIGN`                                                               | `monitor during the pilot`   |
| Split a day into many trips to exceed that day’s cap                 | Remaining cap is aggregated across trips under the per-driver/campaign/day advisory lock                          | `PREVENTED BY THE DOCUMENTED DESIGN` except for G8’s midnight allocation                           | `monitor during the pilot`   |
| Two concurrent worker calculations jointly exceed the same daily cap | `pg_advisory_xact_lock` covers the read-remaining-cap/write-calculation critical section                          | `PREVENTED BY THE DOCUMENTED DESIGN`                                                               | `monitor during the pilot`   |
| A positive reversal row accidentally increases the displayed balance | Positive reversal amounts are subtracted by type in every balance and campaign ledger-net summary                 | `PREVENTED BY THE DOCUMENTED DESIGN`                                                               | `monitor during the pilot`   |
| Replay the same gateway webhook event ID                             | `payment_events.provider_event_id` is unique and duplicate delivery is a 200 no-op                                | `PREVENTED BY THE DOCUMENTED DESIGN`; different event IDs for one transaction remain covered by G6 | `before the dependent slice` |
| Purge raw GPS evidence during the 8–12 week pilot                    | Default ping retention is 12 months; calculations and ledger facts persist indefinitely                           | `PREVENTED BY THE DOCUMENTED DESIGN` at the stated default                                         | `monitor during the pilot`   |

---

# 1. Five highest-risk money-path scenarios

1. **Single-admin retroactive repricing and self-approval.** The built recompute path intentionally uses current terms, while the architecture has neither immutable correction authority nor separation between obligation creation and payment approval.

2. **Phone movement substituted for branded-vehicle movement.** A plausible real route in the wrong vehicle defeats every documented GPS-plausibility check and can consume the full daily cap.

3. **Duplicate or redirected manual payout run.** The bank transfer sits outside a defined reservation/reconciliation state machine; one crash or partial result can pay successful lines twice.

4. **Fraud hold released by acknowledgement or missing assessment.** The ordinary transition into “under review” removes the `open` status named by the release predicate.

5. **Campaign funding disconnected from driver liability.** A paid invoice and advertiser budget do not prove that the platform has funded the maximum liability created by accepted offers, assignments, caps, and expansions.

# 2. Three invariants the architecture must state and preserve

1. **Funded-liability invariant.**

   For every campaign and every committed scope version:

   `paid/held/pending/available driver liability + reserved maximum liability for active accepted scope ≤ confirmed campaign funding + explicitly approved platform subsidy/credit`.

   Every offer, assignment, payout-rule change, expansion, pause, and cancellation must have an immutable effective version or cutoff.

2. **Exactly-once external-settlement invariant.**

   Every bank receipt, refund, and payout transfer maps to one immutable external transaction identity. A ledger entry may belong to at most one active or completed payout line; the line snapshots a verified beneficiary-account version and becomes `paid` only after line-level reconciliation. No actor may both originate a positive correction or cash-movement instruction and approve its settlement.

3. **Fail-closed eligibility-and-release invariant.**

   Release requires affirmative, current evidence: bounded trip timing, a current completed fraud assessment, no durable unresolved hold, correct per-Lagos-day cap allocation, and a net available balance after reversals. Absence of a flag, job result, payment row, or reconciliation result must never be interpreted as approval.

# 3. Claims that cannot be verified without code, tests, or operational evidence

* Whether `recorded_at` is monotonic and bounded by server-observed trip start/end and receipt times.
* Whether the payout engine uses server session duration or client ping timestamps for every payable interval boundary.
* Whether assignment creation takes a vehicle lock or has a database constraint beyond the documented service-layer check.
* Whether the database prevents more than one active/unended trip per driver, vehicle, assignment, or device.
* Whether identical or time-shifted ping payloads are detected across different trips or accounts.
* Whether stationary grace is cumulative, indefinitely resettable, or protected by movement hysteresis.
* Whether repeated and concurrent `recompute-day` requests converge to zero additional differential after the first correction.
* Whether every path that produces a payout calculation requires a current successful fraud evaluation, including admin recompute endpoints and worker repair paths.
* Whether existing summary and future payout-run queries net every reversal/adjustment type consistently.
* Whether the real bank process already has two signers, immutable upload files, transaction-reference uniqueness, or statement reconciliation not recorded in the architecture.
* Whether manual KYC operations detect duplicate NINs, driver licences, vehicle registrations, bank accounts, devices, or reused installation photographs.
* The actual NGN losses: R, H, campaign budgets, invoice totals, available bank cash, and pilot vehicle count remain unset or open.

# 4. Verdict

The core ledger, cap-concurrency, write-once calculation, and retry design do not require replacement. The required fixes are targeted additions: immutable/effective-dated money terms, a funded-liability authorization, a fail-closed fraud decision, database-enforced exclusivity, and explicit receipt/payout/refund reconciliation state machines.

**TARGETED CORRECTIONS REQUIRED**
