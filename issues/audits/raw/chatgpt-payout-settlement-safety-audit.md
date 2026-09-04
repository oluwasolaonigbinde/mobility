---
source_surface: ChatGPT
project: TSS
conversation_id: 6a967de6-be28-83ea-b93f-c790092584de
displayed_title: Audit payout settlement safety
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit payout settlement safety

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict

**RED — do not enable live disbursement at this commit.**

The calculation, fraud-release, correction, debt, and reconciliation layers are materially stronger than the earlier design packet, but the integrated money path still has:

1. **A confirmed high-severity payout-allocation defect:** the daily cap is consumed in processing/lock-winner order, not necessarily in chronological trip order.
2. **A confirmed critical hold-to-submission race:** a fraud hold opened after reservation does not stop submission.
3. **A confirmed high-severity terminal-failure dead end:** a permanently failed transfer remains actively reserved forever and can block unrelated correction/fraud debt for the driver and currency.
4. **A critical live-provider gate:** external submission happens before durable local submission evidence exists, so exactly-once cash movement depends entirely on provider idempotency.
5. **A medium schema-authority gap:** currency is not part of the acceptance-time binding, and the database does not make the principal payout authorities append-only.

The built-in HTTP path cannot currently send money because it always resolves `DisabledDisbursementAdapter`; therefore, these defects are not presently causing real transfers through this commit. Replacing that adapter before closing the first four items would be unsafe. `app/api/v1/disbursements.py:1-31, 116-194`.

## Provenance and execution limitation

The branch head was verified as exactly `637841d95493bcc24334356da42097fa53a5d16f`, and its Git tree was complete and untruncated.

The private repository could not be cloned into the execution sandbox because authenticated Git transport was unavailable. I therefore inspected every cited file through the GitHub connector at the immutable commit ref rather than claiming a local checkout I did not have. I made no repository writes, invoked no provider, and removed the temporary scratch directory. This limitation means the static findings below are confirmed from code, but the PostgreSQL races listed later still require executable evidence.

I ran three isolated deterministic checks:

* A 60-minute interval crossing Lagos midnight split into exactly `1,800 + 1,800` seconds.
* Two one-second components at ₦18/hour produced one authoritative half-up total of `₦0.01`, allocated `₦0.01 + ₦0.00`, avoiding double rounding.
* With a one-hour cap, ₦1,000/hour earlier work and ₦1,800/hour later work produced either `₦1,000` or `₦1,800` solely from processing order: an `₦800` day-level difference.

No repository pytest/PostGIS suite was executed in this environment.

# End-to-end money state machine

```text
ACTIVE PAYOUT RULE
    │
    ├─ append immutable-numbered revision
    │
    └─ campaign offer
          │
          └─ driver accepts
               └─ acceptance-time AssignmentRuleBinding
                    rates / cap / formula / eligibility
                    premium + exclusion geometry
                    campaign payment window
                    [currency is not frozen here]

TRACKING
    → ENDED
    → SEALED
    → route analytics
    → replay evidence
    → current fraud assessment
    → impression authority
    → payout calculation

PAYOUT CALCULATION
    ├─ blocked / insufficient_data → no positive ledger credit
    └─ calculated, amount > 0
          → EarningsLedgerEntry(PENDING)

PENDING
    ├─ current successful assessment + no active hold + release due
    │      → AVAILABLE
    └─ active/stale fraud state
           → stays PENDING
           ├─ hold dismissed → eligible for release
           ├─ seven days → escalation only, never automatic release
           └─ hold confirmed after release
                  → append REVERSAL
                  → carry-forward debt obligation

CORRECTION
    draft order
    → submitted by maker
    → approved by different checker
    → re-project/fingerprint under locks
    → execute
    → append ADJUSTMENT or REVERSAL
    → original calculation and ledger history retained

AVAILABLE POSITIVE CREDIT
    → payout batch RESERVED
    → different admin APPROVES
    → provider SUBMITTED
         ├─ verified SUCCEEDED
         │      → line SUCCEEDED
         │      → ledger PAID
         └─ verified FAILED
                → line FAILED
                → ledger remains AVAILABLE
                → reservation remains active
                → current dead-end

FUTURE CREDIT WITH DEBT
    → allocate against oldest outstanding obligations
    → source credit REVERSED or split with append-only remainder
```

The acceptance binding contains rates, cap, formula, resolved eligibility, frozen geometry, stationary-policy marker, and payment window. It does not contain currency. `app/models/payout.py:288-390`.

# Confirmed findings and financial exposure

## 1. HIGH — the daily cap is allocated by processing order, not chronological trip order

### Evidence

For each trip, payout-v3:

1. Acquires the driver/campaign/Lagos-day advisory lock.
2. Reads payable seconds already persisted by other trips.
3. Subtracts those seconds from the cap.
4. Fills only the current trip’s slices chronologically.

That is chronological **within the current trip**, but not across trips. `app/services/payouts.py:2160-2265`.

By contrast, the correction/recompute authority explicitly locks all overlapping trips and then sorts them by `(started_at, id)` before allocating the shared cap. `app/services/payouts.py:3230-3295`.

The normal unprocessed-trip sweep orders trips by `(ended_at, id)`, not `(started_at, id)`. `app/services/trip_processing.py:755-810`.

More decisively, the focused race test deliberately accepts either trip as the cap winner. It asserts only allocations `[900, 1800]` and a total of 2,700 seconds; it does not assert which chronological trip receives which allocation. Its own comment says one serialization produces one assignment and the other serialization reverses it. `tests/test_payouts_v3.py:1305-1350`.

### Exact transaction sequence

Assume a one-hour cap for the same driver, campaign, and Lagos day:

* Trip A starts at 09:00, qualifies at ₦1,000/hour.
* Trip B starts at 10:00, qualifies at ₦1,800/hour.
* Economically correct chronological result: A consumes the cap and earns ₦1,000; B earns zero.

The bad serialization is:

1. **T-B** begins processing Trip B.
2. T-B acquires the day advisory lock.
3. T-B reads `consumed_before = 0`.
4. T-B assigns all 3,600 payable seconds to B and commits `₦1,800`.
5. **T-A** subsequently acquires the day lock.
6. T-A reads `consumed_before = 3,600`.
7. T-A receives zero.
8. The ledger has paid ₦1,800 where the declared chronological computation would pay ₦1,000.

The day cap itself is not exceeded, so the current race test passes. The economic allocation is nevertheless wrong.

### Exposure

For a single day, the difference is approximately:

```text
cap hours × absolute rate difference between displaced seconds
```

The scratch example produced an ₦800 error from one hour. Frozen assignment rates can differ, and base versus premium slices can differ, so this can cause either:

* **Overpayment** when later, higher-rate work consumes the cap first; or
* **Underpayment** when later, lower-rate work displaces earlier, higher-rate work.

Once the entry becomes paid, repair requires an approved correction and potentially carry-forward debt. It is not self-healing: only the correction path re-establishes canonical start-time ordering.

### Smallest safe fix

Under the day advisory lock, refuse to calculate a trip while any earlier-started sealed trip overlapping that Lagos day lacks an authoritative calculation. Return a retryable `PAYOUT_DAY_PREDECESSOR_UNPROCESSED`, process the predecessor, then retry.

Changing only the sweep’s `ORDER BY` is insufficient because direct jobs and multiple workers can still race. The invariant must be enforced in the calculation transaction.

---

## 2. CRITICAL — a fraud hold opened after reservation does not stop provider submission

### Evidence

Reservation correctly acquires each trip’s fraud-hold scope, locks debt and ledger rows, and checks for an active hold before creating the frozen line. It does **not** require a currently successful fraud assessment; it only checks the hold table at that instant. `app/services/disbursements.py:190-302`.

Approval and submission subsequently lock only the batch and batch lines. Submission verifies the frozen instruction, then calls the provider. It does not reacquire trip fraud locks, reload the current assessment, or recheck active holds. `app/services/disbursements.py:419-492`.

This is inconsistent with release, which correctly requires both:

* A current successful assessment; and
* No active hold,

under the trip’s fraud scope. `app/services/earnings_release.py:75-134`.

### Exact race sequence

1. A trip has a current clean assessment and no hold.
2. Release changes its credit from `PENDING` to `AVAILABLE`.
3. **T1 — reserve** acquires the trip fraud scope, observes no hold, inserts an active `RESERVED` line, and commits.
4. **T2 — fraud** runs after T1 releases the trip scope. New evidence, configuration drift, replay evidence, or an investigator opens/acknowledges a hold and commits it.
5. **T3 — approve** approves the frozen batch without consulting trip fraud state.
6. **T4 — submit** locks the batch and lines only, calls the provider, and submits the full frozen amount.
7. The authoritative hold exists, but it has no settlement effect.

This is a classic time-of-check/time-of-use gap between reservation and cash submission.

### The hold can also block its own confirmation

Confirmation changes the flag to `CONFIRMED`, appends a fraud reversal, and then calls `record_reversal_obligation` in the same service operation. `app/services/fraud_holds.py:157-248`; `app/services/earnings_release.py:285-392`.

Debt creation rejects **any** active non-succeeded reservation for the same driver and currency. `app/services/payout_debt.py:108-145`.

Therefore, while the line is reserved, submitted, or failed:

1. Investigator attempts to confirm fraud.
2. The service changes the flag and creates a reversal in the current transaction.
3. Debt creation finds the active reservation and raises `PAYOUT_DEBT_ACTIVE_RESERVATION`.
4. The fraud-confirmation operation cannot complete successfully.

The reservation can thus both permit payment despite a hold and prevent the hold’s final economic resolution.

### Exposure

The maximum immediate exposure is the **entire reserved line or batch amount** submitted after the hold arose.

A later reversal does not undo cash already transferred. It merely creates recovery debt, contingent on future earnings and on the reservation first reaching `SUCCEEDED`.

### Smallest safe fix

Before any external submission:

1. Acquire all affected trip fraud locks in stable trip-ID order.
2. Require a current successful assessment for every nonterminal line.
3. Recheck active holds.
4. Lock debt and ledger rows in the existing global order.
5. Persist a durable submission intent before leaving the transaction.

A newly held pre-provider line should transition to an auditable cancelled/void state that releases its reservation. A submitted or unknown-outcome line must remain blocked while the provider is queried or cancelled.

Fraud confirmation must be able to commit authoritative fraud state even when a payout line is active. At minimum, the active line should be atomically marked blocked/cancelled when it has no provider reference; unknown provider outcomes require a separate pending-recovery state rather than aborting the fraud decision.

---

## 3. HIGH — terminal provider failure strands the credit and blocks unrelated debt/corrections

### Evidence

On verified failure:

* The line changes to `FAILED`.
* The ledger is not changed from `AVAILABLE`.
* The reservation is not released. `app/services/disbursements.py:560-680`.

The database expressly requires every non-void state—including `FAILED`—to have `reservation_active = true`. `app/models/disbursement.py:86-126`.

The only recovery operations are:

* Retry the same frozen instruction, idempotency key, and provider reference; or
* Void a batch only while it is still entirely pre-provider `RESERVED`.

A failed line cannot be voided, released, re-bound to a corrected payee account, or placed in a new batch. `app/services/disbursements.py:744-875`.

Debt creation rejects any active non-succeeded line for the same driver and currency, not merely for the same trip or ledger entry. `app/services/payout_debt.py:108-145`.

The balance projection simultaneously counts every `AVAILABLE` credit as released and batch-payable without subtracting active reservations. `app/services/payout_debt.py:203-283`.

### Exact failure sequence

1. A valid `AVAILABLE` ₦50,000 credit is reserved.
2. The provider returns a verified terminal failure, for example an irrecoverably closed account.
3. The line becomes `FAILED`; the ledger remains `AVAILABLE`; `reservation_active` remains true.
4. The balance surface continues to report ₦50,000 as released/batch-payable.
5. A second batch cannot reserve it because of the active-reservation unique index.
6. Void refuses because the line has a provider reference and is no longer `RESERVED`.
7. Retry must use the same account snapshot and the same provider reference.
8. A subsequent unrelated fraud confirmation or negative correction for that driver/currency attempts to create debt.
9. `record_reversal_obligation` finds the failed line and raises.
10. Both the original credit and subsequent corrective authority are operationally blocked.

### Exposure

* The failed amount can remain stranded indefinitely.
* All new reversal debt for that driver/currency can be blocked.
* Operator surfaces state that money is available when it is not batchable.
* Manual off-ledger payment creates a serious late-success/double-payment risk if the provider later changes or corrects the original outcome.

### Smallest safe fix

Add an explicitly evidenced terminal state, for example `terminal_failed` or `cancelled_after_failure`, which:

1. Requires cryptographically verified provider evidence that the transfer cannot later succeed.
2. Sets `reservation_active = false`.
3. Retains the old line and all evidence.
4. Permits a new line linked to the old one, with a newly frozen account/version and a new idempotency key.
5. Distinguishes terminal failure from an **unknown** outcome; unknown outcomes must remain reserved and pollable.
6. Removes authoritative terminal-failed lines from the debt-blocking query.
7. Reports `available`, `reserved/in flight`, `terminally failed/retryable`, and `batch-payable` separately.

---

## 4. CRITICAL LIVE GATE — no durable evidence exists before the provider call

### Evidence

`submit_payout_batch`:

1. Opens/uses the database transaction.
2. Locks the batch and lines.
3. Builds all provider instructions.
4. Calls `adapter.submit_batch`.
5. Only after the external call returns does it store provider references and change local statuses to `SUBMITTED`.
6. The API commits afterward. `app/services/disbursements.py:419-492`; `app/api/v1/disbursements.py:116-148`.

A `SUBMITTED` batch replay also rebuilds instructions for **all** lines, not only unresolved lines. Consequently, a partially reconciled batch can resend previously succeeded or failed instructions.

### Exact crash sequence

1. Local line is `RESERVED`; no provider reference exists.
2. Application calls the provider.
3. Provider accepts the transfer and durably creates cash movement.
4. Before the local flush/commit, any of the following happens:

   * Process crash;
   * Database connection failure;
   * Provider response validation failure;
   * Unique provider-reference conflict;
   * Transaction rollback.
5. Local state remains `RESERVED`.
6. Operator retries submission.
7. The provider receives the same economic instruction again.

The database cannot determine whether the first call succeeded.

### Exposure

Without durable provider-side idempotency, exposure is up to the **entire retried line or batch amount**.

Even with provider idempotency, safety depends on facts absent from this repository:

* Key uniqueness scope;
* Retention lifetime;
* Whether duplicate calls return the original transfer reference;
* Whether lookup by idempotency key is available after timeout;
* Whether idempotency survives provider failover;
* Whether retries with the same key and changed metadata are rejected.

### Smallest safe fix

Introduce an append-only submission-attempt/outbox authority:

1. Commit an immutable `submission_intent` for each unresolved line before external I/O.
2. Have a worker claim intents and perform provider calls outside the business transaction.
3. Record every request attempt, timeout, response fingerprint, and provider reference append-only.
4. After an ambiguous outcome, query the provider by the idempotency key before resending.
5. Send only unresolved lines; never include succeeded or authoritative terminal-failed lines.
6. Keep one immutable economic instruction per line while allowing versioned provider attempts.

This still requires durable provider idempotency. An outbox alone cannot atomically join PostgreSQL and an external payment system.

---

## 5. MEDIUM — frozen terms and money evidence are not completely schema-immutable

### Currency is not frozen

The acceptance binding freezes rates, cap, formula, eligibility, geometry, and payment window, but it has no currency column. `app/models/payout.py:288-390`.

Payout-v3 reloads the current `CampaignPayoutRule` and uses `rule.currency` in:

* The input fingerprint;
* The calculation currency;
* The resulting ledger currency.

`app/services/payouts.py:2160-2190, 2410-2445`.

The supported service correctly rejects currency mutation once a payout-v2 rule has entered the revision model. `app/services/payouts.py:631-681`.

That protects the normal API path, but it is not the same as freezing currency in the acceptance contract.

### Money authorities are not protected by database immutability triggers

The reviewed payout migration defines checks, unique constraints, and foreign keys, but payout calculations and earnings ledger entries have no equivalent of an append-only database trigger. Several payout authority links use cascading parent deletion. `alembic/versions/0010_payouts_and_earnings.py:286-424`.

This contrasts with the DSR evidence migration, which explicitly creates triggers rejecting update/delete of immutable evidence. `alembic/versions/0062_data_subject_requests.py:120-225`.

I found no supported DSR path that deletes the money rows—the current DSR service inventories records and records external erasure or retained-exception evidence rather than performing those deletions. `app/services/data_subject_requests.py:350-720`.  Therefore this is not an ordinary user/API exploit, but it is a failure of the claimed absolute immutability boundary against privileged SQL, buggy maintenance code, or future lifecycle work.

### Exposure

* A privileged write can re-denominate accepted-but-unprocessed work because currency is taken from the rule row.
* A privileged write can alter a frozen binding, calculation, ledger amount, or metadata without an immutable database event.
* Parent deletion graphs do not provide a truthful guarantee that financial evidence will survive every deletion path.

### Smallest safe fix

* Add currency to `CampaignPayoutRuleRevision` and `AssignmentRuleBinding`.
* Include it in the offer fingerprint.
* Price payout-v3 exclusively from `binding.currency`.
* Add database guards that make binding/calculation/ledger economic fields immutable.
* Permit only enumerated status transitions through guarded functions/triggers.
* Replace cascade relationships from deletable domain parents to economic authority with `RESTRICT` or nullable snapshot references as appropriate.
* Require every correction through the append-only correction-order path.

# Invariants verified as correct

## Formula and accepted terms

The normal acceptance path creates the binding in the acceptance transaction and freezes payout-v3 rates, cap, eligibility parameters, premium/exclusion geometry, formula version, offer fingerprint, and campaign window. Later revisions do not automatically alter those fields. The service also retires direct mutation of payout-v2 value fields once the revision chain exists.

The exception is currency, described above.

## Lagos-day allocation

Lagos-day keys are derived from the eligibility breakdown, sorted, and locked in stable day order before cap consumption is read. Cross-midnight allocation is per Lagos civil day rather than UTC day. `app/services/payouts.py:2195-2248`.

The scratch check and the focused test both produced the expected 1,800 seconds on each side of Lagos midnight. `tests/test_payouts_v3.py:1352-1384`.

The cap ceiling is protected; the defect is which trip receives the cap.

## Base, premium, exclusions, and stationary time

The classifier uses integer-second intervals, deterministic exclusion precedence, frozen premium/exclusion geometry, and fail-closed treatment of unusable gaps, poor accuracy, and teleport contamination. Premium classification is attached to eligible slices before tier pricing. The stationary detector is rolling and hysteretic rather than paying an entire stay-point interval merely because one ping moved. `app/services/payout_eligibility.py:1-720`.

I found no path that knowingly prices excluded or authoritative stationary seconds as payable. This still needs real PostGIS boundary tests for polygons, holes, and exact-edge points.

## Rounding

The implementation:

* Counts integer seconds;
* Applies the cap before pricing;
* Computes base and premium raw amounts;
* Quantizes the authoritative total once with half-up semantics;
* Allocates components so they exactly reconcile to that total.

The focused test explicitly covers the half-kobo case where independently rounding both components would overstate the total. `tests/test_payouts_v3.py:1388-1425`.

## Fraud release and seven-day escalation

Release reacquires the trip fraud scope and revalidates the full current assessment fingerprint and active-hold state. A stale/missing assessment or active hold leaves earnings pending. `app/services/earnings_release.py:75-134`.

A dismissed hold ceases to be active and can release once assessment evidence is current. A confirmed hold posts a separate positive reversal whose economic sign is subtractive; it does not mutate the original credit.

The configured review SLA is seven days. The due action only records `escalated_at` and audit evidence; it does not automatically release flagged money. `app/core/config.py`, `fraud_review_sla_days = 7`; `app/services/earnings_release.py:145-221`.

## Maker-checker and reconciliation separation

* Batch approver must differ from batch maker, enforced in service and database constraint.
* Polling reconciler must differ from both maker and approver.
* Correction order approver must differ from creator.
* Correction execution re-projects the day and rejects a changed fingerprint before writing money.

`app/services/disbursements.py:330-418, 540-575`; `app/models/disbursement.py:45-65`; `app/services/payout_corrections.py:1-820`.

## Append-only corrections

The supported correction path calculates a day target, compares it to the posted position, and appends an adjustment or reversal. It does not edit the original calculation. Executed-order replay returns the recorded result rather than writing another differential. The public direct-recompute route is retired with a conflict response.

## Carry-forward debt

Debt is scoped by driver and currency, obligations are tied to source reversals, and allocation records settlement and obligation allocation evidence. New credits are consumed deterministically, with an append-only remainder where required. The arithmetic conservation model is coherent. `app/services/payout_debt.py`.

The active-reservation scope is too broad, as described in Finding 3.

## Reservation, partial reconciliation, and paid finality

* Frozen lines contain amount, currency, payee version, account version, instruction fingerprint, and deterministic idempotency key.
* A partial unique index allows only one active line per ledger entry.
* Provider evidence is applied per line.
* Provider event IDs are replay protected.
* Verified success changes `AVAILABLE → PAID`.
* Failure evidence cannot downgrade a `PAID` ledger entry.
* A succeeded line is terminal against later failure evidence.

`app/services/disbursements.py:190-390, 560-710`; `app/models/disbursement.py:86-145`.

# Gaps requiring real PostgreSQL evidence

These should be demonstrated against the exact migrated schema using multiple independent connections and barriers at the specified points:

1. **Canonical day sequencing:** start a later trip first, pause after it obtains the day lock, then start the earlier trip. Confirm the current build produces the wrong trip assignment; after the fix, the later trip must refuse or wait for its predecessor.

2. **Mixed payout-v2/v3 sequencing:** use different frozen rates and premium tiers, not merely equal-rate seconds. Assert each trip’s allocation and final amount, not only `sum(payable_seconds) <= cap`.

3. **Reserve–hold–submit race:** commit reservation, then open/acknowledge a hold, then attempt approval/submission. Submission must refuse before any adapter invocation.

4. **Assessment drift after reservation:** change the fraud flag watermark, replay authority, analytics fingerprint, or configured fraud formula after reservation. Submission must fail closed.

5. **Fraud confirmation with an active line:** verify that authoritative fraud state can commit without losing evidence while the line is reserved, submitted, failed, succeeded, or unknown.

6. **Permanent failure closure:** apply verified terminal failure, release the reservation, create a linked replacement line, and then deliver late success evidence for the old line. The old success must become a reconciliation incident, never a second ordinary payment.

7. **Provider-call crash:** force process termination after provider acceptance but before local commit. Recovery must query by the durable idempotency key and must not create another transfer.

8. **Partial batch replay:** succeed one line, leave another submitted, then replay submission. The adapter must receive only the unresolved line.

9. **Correction versus reservation:** interleave positive and negative day corrections with reserve, release, provider success, and debt allocation. Confirm conservation and absence of deadlocks.

10. **DDL evidence:** query the deployed catalog for every check, partial unique index, foreign key action, and trigger. Attempt forbidden updates/deletes directly to prove the intended database boundary rather than relying on ORM conventions.

# Provider and live-settlement gates

Live settlement should remain disabled until all of the following are evidenced:

1. **Durable per-line idempotency.** Duplicate requests with the same key must return the original transfer and reference indefinitely for the required financial-retention period.

2. **Lookup after ambiguous outcomes.** The provider must support authoritative lookup by idempotency key and transfer reference after timeout, disconnect, or failover.

3. **Signed, replay-protected reconciliation.** Webhook signatures, event identifiers, timestamp tolerance, key rotation, and poll authentication need staging evidence.

4. **Explicit outcome taxonomy.** The adapter must distinguish:

   * retryable rejection;
   * authoritative terminal failure;
   * accepted/submitted;
   * succeeded;
   * unknown/ambiguous.

5. **Stable retry semantics.** The current code requires a failed retry to return the exact original transfer reference. The chosen provider must support that, or the model must support versioned attempts.

6. **Crash and duplicate drills.** Demonstrate provider acceptance followed by local rollback, duplicate submission, delayed success after failure, duplicate and reordered callbacks, partial success, and provider-reference collision.

7. **No submission while held or stale.** Adapter invocation must be instrumented so a PostgreSQL race test can prove it was never called when any line failed the final fraud gate.

8. **Operational reconciliation.** Unknown and terminal-failed lines need explicit queues, age alerts, maker-checker repair, and immutable operator evidence. Manual off-ledger transfers cannot be the recovery mechanism.

# Prioritized smallest fixes

**P0 — before any provider is enabled**

1. Add the canonical predecessor gate to per-trip daily-cap allocation.
2. Revalidate current fraud assessment and active holds at both reservation and submission.
3. Add an authoritative terminal-failure/cancellation state that releases reservations and supports linked replacement instructions.
4. Add durable submission intents/attempts and provider lookup-before-resend.
5. Submit only unresolved lines.

**P1 — before declaring the ledger immutable**

6. Freeze currency in the revision, offer, and assignment binding.
7. Add database immutability guards for binding, calculation, ledger economic fields, provider instructions, and reconciliation evidence.
8. Remove cascade-dependent preservation from money authorities.
9. Split balance reporting into available, actively reserved, submitted/unknown, terminal-failed, paid, and debt.

**P1 — regression evidence**

10. Change the mixed-engine race test to assert trip identity and amount under canonical start order. The current assertion that either allocation is acceptable encodes the bug as expected behaviour.

# Can historical payouts be silently repriced?

**Through supported application endpoints and services: no.**

Already-created calculations are reused rather than overwritten, normal payout-v2 value and currency mutation is retired once revisions exist, and corrections append differential ledger entries instead of editing historical amounts.

**As an absolute system or database guarantee: also no—the system cannot truthfully claim that silent repricing is impossible.**

A privileged database/ORM write can alter the unfenced binding, calculation, or ledger authority. In addition, accepted-but-unprocessed payout-v3 work reads currency from the current rule because currency is absent from the frozen binding. Such work can therefore be silently re-denominated by an out-of-band rule-row change.

The precise conclusion is:

> **Posted payouts are not silently repriced by the supported workflow, but schema-level silent alteration is not prevented, and accepted-but-unprocessed commitments are not completely frozen because currency remains outside the binding.**
