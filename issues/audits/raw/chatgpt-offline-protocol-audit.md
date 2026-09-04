---
source_surface: ChatGPT
project: none
conversation_id: 6a968442-15ec-83ea-92f8-d2089acdca32
displayed_title: Audit offline protocol
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit offline protocol

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict

**Overall verdict: FAIL — release-blocking for any claim that Cardvert provides lossless offline trip evidence or that initial payout always waits for all captured evidence.**

The implementation is strong on ordinary retry safety and duplicate suppression, and it accurately limits itself to foreground-only tracking. The failure is in trip finality: a trip can become irrevocably sealed—and therefore eligible for analytics and payout—without a content-bound proof that every client batch reached the server.

| Required conclusion                                  | Audit result                                                                                                                                                                                                                                                                                                            |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Can offline data be lost?**                        | **Yes.** Ordinary network loss does not delete a queued batch, but evidence can be stranded in local deadletters, omitted after grace sealing, quarantined after sealing, or become inaccessible through IndexedDB/key failure. GPS points are also intentionally not captured while hidden or after an offline reload. |
| **Can an initial trip be paid twice?**               | **No code-confirmed automatic double-payment path was found.** Stable ingest keys, database uniqueness, row locking, payout-calculation uniqueness, and trip-wide ledger guards protect the normal processing path. This is code-level evidence, not a production concurrency proof.                                    |
| **Can a trip be paid from incomplete evidence?**     | **Yes.** The server can seal after its default 600-second grace period despite a missing watermark, and the immediate seal predicate compares only a client-supplied batch count.                                                                                                                                       |
| **Are unsupported background-tracking claims made?** | **No.** The ADR and implementation explicitly describe a visible, foreground-only PWA; the service worker does not collect GPS or perform background delivery.                                                                                                                                                          |

The exact GitHub commit `637841d95493bcc24334356da42097fa53a5d16f` was resolved and all source reads were revision-pinned. The requested feature branch pointed at that revision; the default branch was not used as a substitute.

## Verification scope

This was a read-only code and committed-test audit. I did not clone or modify the repository.

The existing synthetic Playwright journey was **not executed** because the available audit environment did not expose an already prepared Cardvert application, database, and browser runtime; I did not install dependencies. The journey itself is opt-in, rejects real-looking credentials, and mocks geolocation, wake lock, sessions, and backend requests, so even a passing run would remain synthetic rather than physical-device evidence. `frontend/e2e/w403b-synthetic-pilot-journey.spec.ts:1-209`.

Committed unit, backend, and browser tests were read as specifications, but their presence is not reported as a passing result at this SHA.

# Protocol timeline

## 1. Start

The browser requires installed/standalone mode, a visible page, location permission, a wake lock, IndexedDB, an exclusive Web Lock, an online session, and server authority before enabling Start. It does not optimistically begin a trip on an ambiguous POST response; it reconciles through the current-trip endpoint. `frontend/src/lib/pwa/capability-contract.ts:98-193`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:500-700`.

The server commits Start before returning. Therefore, loss of the response after commit is recoverable through the current-trip read rather than a blind second Start. `app/api/v1/trips.py:63-83`; `frontend/src/app/driver/actions.ts:68-143`.

## 2. GPS capture

While visible, the page runs `watchPosition`. Each fix is sent to the encrypted IndexedDB queue; flushing occurs on a threshold and timer. An important UI detail is that `setLastFix(position)` occurs **before** `queue.addPing(...)` completes, so the displayed fix is not itself proof of durable storage. If the IDB write fails, tracking stops and an error is shown. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:376-432`.

A queue cut creates one UUID batch, increments `batchesCut`, stores the encrypted batch and updated metadata, and removes its pending ping records in one IDB transaction. `frontend/src/lib/trips/ping-queue.ts:430-472`.

## 3. Offline interruption

If the already-loaded foreground page loses network access, capture can continue into IndexedDB. The service worker does not send the data in the background.

An **offline navigation/reload is different**: the service worker returns a static 503 reconnect page rather than an executable tracking application. Previously queued IDB records are not intentionally deleted, but no GPS capture or retry occurs until an online app load succeeds. `frontend/public/driver-sw.js:1-7,20-28,59-75`.

## 4. Retry

The exact cut batch and key remain in IndexedDB after transport errors, 5xx responses, malformed acknowledgements, or other ambiguous outcomes. Local deletion occurs only after an acknowledgement that matches the requested trip, expected accepted count, and accepted/duplicate/quarantined result. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:320-390`; `frontend/src/app/driver/actions.ts:200-286`.

On the server, the same idempotency key and canonical payload returns the original acknowledgement. Reuse of the key with a different canonical payload is rejected. This remains true across the live/sealed boundary because deduplication is checked before deciding whether a new arrival must be quarantined. `app/services/trips.py:535-740`.

## 5. End

End first stops the GPS watch, then runs the drain. It reads:

* `meta.batchesCut`
* `meta.pingsRecorded`
* remaining unsynced pings
* local deadletters

It sets `clientComplete` only when storage is healthy and both unsynced and deadletter counts are zero. The driver is nevertheless allowed to confirm an incomplete End, and the client sends the batch count, ping count, and `clientComplete=false`. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:737-805`.

If the End result is ambiguous, the browser reads current server authority. If the trip is still active, it attempts to resume foreground capture; if no active trip remains, it completes the local End without blindly issuing another End. While authority is unresolved, capture remains paused and the writer lock remains reserved. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:650-737`.

## 6. Seal

The intended invariant should be:

> `sealed ⇒ the server has the exact complete set of batches the client durably cut`

The implemented invariant is only:

```text
sealed ⇒ server_batch_count >= client_batch_count
         OR recovery grace expired
```

`client_complete` and `client_ping_count` are explicitly treated as diagnostic only. There is no manifest of batch IDs or payload hashes. `app/services/trips.py:393-416`.

If that count test is not met, the trip stays `ended` and can accept late live batches. After the configured grace period—default 600 seconds—the worker force-seals the trip even if its watermark was never satisfied. Subsequent arrivals go to quarantine. `app/services/trip_processing.py:806-842`; `app/core/config.py:105-106`.

## 7. Processing and payout

The worker blocks processing unless the trip is `sealed`. Analytics calculated before sealing are treated as potentially stale and recomputed over the sealed live set before the money chain proceeds. `app/services/trip_processing.py:125-190`.

That is a real safety gate, but it is only as sound as sealing. A `GRACE_EXPIRED` trip is still `sealed`, so partial evidence becomes an authorized processing input.

The payout path uses trip locks, a unique payout calculation per trip, version uniqueness, and trip-wide ledger guards. I found no normal retry path that creates a second initial trip-payout entry. `app/models/payout.py:15-33,495-523`; `app/services/payouts.py:1645-1836`.

# Probe results

## 1. Reload with unsent batches — **Partial**

An online reload reacquires the writer lock before restoring the active trip and searches the live queue for leftover trip IDs. A fully offline reload receives the reconnect fallback and cannot capture or retry.

`tripsWithLeftovers()` searches only the main records store. Deadletters are in a separate store and are therefore not discoverable when a trip has no remaining pending/live batch records. `forgetTrip()` likewise operates only on the main records store. A deadletter-only ended trip can consequently remain encrypted locally but disappear from automatic recovery. `frontend/src/lib/trips/ping-queue.ts:508-568`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:430-470`.

## 2. Network loss before request — **Pass for already persisted batches**

Once a batch is cut, a failure before the request reaches the backend leaves the exact batch in IDB. The flush loop breaks without acknowledging or deleting it. Start and End operations use authority reconciliation instead of treating an ambiguous request as a proven success. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:320-390`; `frontend/src/app/driver/actions.ts:68-286`.

This does not protect a GPS fix whose IDB write itself failed.

## 3. Network loss after server commit — **Pass**

For ping batches, the retry uses the same key and payload and obtains a duplicate acknowledgement rather than inserting the batch twice. Start and End reconcile through current-trip authority. API-side worker-enqueue failure does not roll back a committed trip/batch record; sweeps remain the eventual processing path. `app/api/v1/trips.py:63-198`; `app/services/trips.py:620-700`.

## 4. Network loss during End — **Safe from duplicate End, but creates a capture gap**

The browser has already stopped its GPS watch before making the End call. An ambiguous result is reconciled. If the server remains unreachable, the tracker stays authority-uncertain and stopped until it can determine whether the trip is active or ended. Queued evidence is retained, but new locations are missed during that uncertainty period. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:700-805`.

If End committed but unsent batches remain offline longer than the grace period, the server can seal and process without them; their eventual retry is quarantined.

## 5. Stable idempotency keys — **Pass**

A UUID is minted once at the atomic batch cut and the complete encrypted batch survives reload and retry. The server has a unique trip/idempotency-key constraint and compares a canonical payload hash before returning a duplicate acknowledgement. `frontend/src/lib/trips/ping-queue.ts:430-472`; `app/models/trip.py:106-140`; `app/services/trips.py:620-700`.

Server deduplication is key-based. A nonconforming or hostile client could submit the same locations under a new key; that is not a path produced by the audited queue but is outside the idempotency guarantee.

## 6. Atomic batch cuts — **Pass at code level**

The IDB transaction atomically stores the cut batch, advances metadata, and removes selected pending records. Committed tests assert abort rollback and exact partitioning under concurrent add/cut operations. The backend validates the whole batch before inserting it in one database transaction. `frontend/src/lib/trips/ping-queue.ts:430-472`; `frontend/src/lib/trips/ping-queue.test.ts:360-800`; `app/services/trips.py:535-740`.

The committed test was not run during this audit.

## 7. Multi-tab contention — **Pass by failing closed**

The tracker requires the origin-scoped Web Lock `cardvert-driver-trip-writer-v2`. Missing, denied, or contended locks disable capture rather than allowing a second writer. Queue migration also requires a Web Lock. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:190-250`; `frontend/src/lib/trips/ping-queue.ts:220-340`.

This protects consistency at the cost of availability. If Web Locks become unavailable after a trip has started, that client cannot safely resume or End the trip.

## 8. IndexedDB failure — **Fail closed, not lossless**

Start and capture are blocked when the queue cannot be opened. A transaction failure during `addPing` stops the GPS watch, but that fix is not retried. The UI has already updated `lastFix` before storage completes.

Encrypted records also become unreadable if their non-extractable queue key is missing. The code throws rather than silently discarding or replacing the key, which is correct fail-closed behavior, but there is no server copy of unacknowledged evidence. `frontend/src/lib/trips/ping-queue.ts:120-220`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:376-432`.

Therefore, browser origin-data clearing, storage eviction, corruption, or key loss can cause physical data loss. That browser behavior still requires device testing.

## 9. Web Locks failure — **Consistency pass; availability fail**

There is no unsafe fallback. Start, resumed capture, and End require the exclusive writer. This prevents concurrent mutation but may leave a server-side trip active and locally unendable from an unsupported browser. `frontend/src/lib/pwa/capability-contract.ts:98-232`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:190-250`.

## 10. Permission denial or revocation — **Partial**

Initial denial blocks Start. A geolocation watch error stops capture and marks permission revoked/unavailable; visibility recovery reprobes location. End itself does not require continued location permission, which is appropriate. `frontend/src/lib/pwa/capability-contract.ts:80-92,98-232`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:376-432`.

There is no physical evidence here that every supported browser reliably emits a watch error or permission transition at the moment of OS-level revocation.

## 11. Visibility degradation — **Intentional evidence gap**

When hidden, the tracker stops the watch and releases the wake lock. When visible again, it reprobes and attempts to resume. It does not claim continuity while backgrounded. This is consistent with the accepted architecture, but GPS evidence for the hidden interval does not exist. `docs/adr/014-production-pwa-capability-contract.md:35-51`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:500-720`.

## 12. Client clock skew — **Confirmed evidence-omission path**

The client sends `new Date(position.timestamp).toISOString()`. The server rejects pings more than 300 seconds in the future and those outside trip start/end tolerances. Validation is all-or-nothing: one invalid ping rejects the entire batch with HTTP 400. `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:390-410`; `tests/test_trips.py:627-679`.

The browser action classifies 400 as terminal, and the tracker moves the whole batch to deadletter. It does not split out the bad sample or automatically retry valid samples. `frontend/src/app/driver/actions.ts:200-286`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:340-370`.

After End, the missing batch prevents a count match, but grace expiry eventually permits processing from the remaining evidence.

## 13. End watermark mismatch — **Fail**

An overreported count leaves the trip ended until the missing batches arrive or grace expires.

An underreported count can seal immediately because the predicate is `server_count >= client_count`, not exact manifest equality. More importantly, the official client permits an incomplete End and sends `clientComplete=false`, but the server ignores that flag. `app/services/trips.py:393-416`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:737-805`.

A reachable example is an End where locally pending, not-yet-cut pings remain after the final drain. `unsyncedCount` detects them, but `meta.batchesCut` does not include them. If the driver confirms the incomplete End and every already-cut batch is on the server, the server count matches and immediate sealing can occur despite those pending pings.

## 14. Late batches while ended — **Pass until grace expires**

An `ended` trip remains inside a live recovery window. Late batches are accepted as live evidence, assignment activity is no longer checked, normal timestamp validation still applies, and an arrival that satisfies the count may seal the trip. `app/services/trips.py:535-740`; `tests/test_trips.py:680-752`.

Once the grace worker wins the seal race, the same batch is no longer late-live evidence; it becomes quarantine evidence.

## 15. Post-seal quarantine — **Pass for immutability**

A new post-seal batch is stored with its canonical key, payload hash, and pings in quarantine. It is not silently added to the live set used by the initial money chain. Stable-key replays are still deduplicated. `app/services/trips.py:620-760`.

The client treats a validated quarantine acknowledgement as durable server receipt and may delete its local batch. That is safe at the byte level because the server now has the canonical quarantine copy.

## 16. Apply/discard behavior — **Controlled, but no automatic financial correction**

Resolution is row-locked and audited. Apply inserts the quarantined batch and pings into the live evidence tables and updates affected metrics; discard records the rejection. A resolved item cannot simply be applied a second time.

Apply deliberately performs **no automatic payout recomputation**. Therefore, valid evidence applied after initial calculation does not produce a duplicate initial payout—but also does not automatically correct an underpayment. `app/services/trips.py:740-1010`.

## 17. Analytics before sealing — **Money chain protected**

Analytics may exist before sealing, but an `ended` trip is blocked from worker money processing. A pre-seal analytics row is recomputed over the sealed live set. `app/services/trip_processing.py:125-190`; `docs/adr/014-production-pwa-capability-contract.md:111-139`.

The residual problem is that the sealed live set itself can be incomplete.

## 18. Quarantine before initial payout — **Immutable but completeness-negative**

Apply is blocked until an initial `PayoutCalculation` row exists. Thus, a valid batch that arrives just after sealing but before the worker computes payout cannot be applied in time to affect that initial calculation. The initial payout necessarily proceeds without it; any later correction requires an explicit separate process. `app/services/trips.py:740-1010`; `tests/test_trip_seal.py:280-520`.

This protects write-once accounting, but it makes premature sealing economically consequential.

## 19. Assignment deactivation during evidence delivery — **Confirmed failure**

While a trip is still active, the server requires the assignment to remain active. A batch retried after assignment deactivation receives HTTP 400 `CAMPAIGN_ASSIGNMENT_NOT_ACTIVE`. Once the trip is ended, that assignment gate is skipped and the same recovery-window evidence would be eligible. `tests/test_trips.py:680-752`.

The official client drains **before** sending End. Consequently:

1. The assignment becomes inactive while the trip has offline batches.
2. The client reconnects and performs its final drain while the trip is still `active`.
3. The server returns terminal 400.
4. The frontend classifies 400 as non-retryable.
5. The whole batch is atomically moved to local deadletter.
6. End then occurs.
7. The client does not automatically retry that batch under the now-permissive `ended` policy.

`frontend/src/app/driver/actions.ts:200-286`; `frontend/src/app/driver/(portal)/track/trip-tracker.tsx:340-370`; `frontend/src/lib/trips/ping-queue.ts:480-568`.

This is a confirmed protocol-level loss from the automatic live-evidence and initial-payout path.

## 20. Unsupported background-tracking claims — **Pass**

The ADR explicitly says foreground-only. Hidden visibility pauses capture. Offline reload does not claim active tracking. The capability contract hard-rejects a background-guarantee row, and the service worker handles only static assets and a reconnect fallback; it does not collect GPS or perform Background Sync delivery. `docs/adr/014-production-pwa-capability-contract.md:24-51`; `frontend/src/lib/pwa/capability-contract.ts:235-240`; `frontend/public/driver-sw.js:1-81`.

# Confirmed loss, duplication, and premature-processing paths

## Confirmed evidence omission or loss

1. **Assignment-deactivation race:** an otherwise valid offline batch is terminally deadlettered while active, even though it would be accepted moments later after End.

2. **Clock-skew batch rejection:** one invalid timestamp causes the entire batch—including otherwise valid pings—to be deadlettered.

3. **Grace expiry:** an incomplete ended trip is force-sealed after the default ten-minute grace. Any later batch is quarantined and excluded from the initial payout.

4. **Incomplete End plus count-only sealing:** the client may explicitly report `clientComplete=false`; the server still immediately seals when the numeric count condition happens to pass.

5. **Deadletter-only reload:** the bytes remain locally encrypted but disappear from automatic leftover discovery once no pending/live batch record remains.

6. **IDB write/key/origin failure:** a current GPS fix can fail before persistence, and unacknowledged local evidence has no redundant server copy.

7. **Visibility and offline-reload gaps:** these do not delete existing bytes, but GPS evidence is never captured during the unavailable period.

## Confirmed duplication paths

**None in the conforming Start → queue → retry → End → process flow.**

Response loss after server commit is handled with stable-key replay or authority reconciliation. Atomic cuts prevent the normal client from re-cutting the same pending record under a second key.

The server’s semantic deduplication is nevertheless limited to idempotency keys. Same-content submissions under deliberately different keys are not the guarantee being enforced.

## Confirmed premature-processing paths

1. `server_batch_count >= client_batch_count` is not proof of exact-set completeness.
2. `client_complete=false` does not block sealing.
3. `client_ping_count` does not block sealing.
4. No batch-ID/hash manifest binds the End watermark to actual server receipts.
5. `GRACE_EXPIRED` produces an ordinary `sealed` trip, which is accepted by the money worker.
6. Post-seal evidence cannot be applied before initial payout calculation and does not automatically recompute money afterward.

The ADR and implementation agree on this design. The central defect is therefore architectural rather than merely an implementation deviation. `docs/adr/014-production-pwa-capability-contract.md:81-139`.

# Browser versus server responsibilities

| Browser responsibility                                | Current result                                                |
| ----------------------------------------------------- | ------------------------------------------------------------- |
| Capture only when foreground capability is supported  | Enforced                                                      |
| Hold one exclusive writer                             | Enforced with Web Locks; fail-closed                          |
| Persist pending evidence and atomically cut batches   | Enforced                                                      |
| Retry the same batch without mutation                 | Enforced                                                      |
| Delete only after a positive server receipt           | Enforced                                                      |
| Build a trustworthy End commitment                    | **Not enforced: only counts are retained/sent**               |
| Preserve and surface terminal evidence across reload  | **Incomplete: deadletter-only trips are not auto-discovered** |
| Avoid presenting a fix as durable before IDB succeeds | **Not enforced: `lastFix` updates first**                     |

| Server responsibility                                                                            | Current result                              |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| Transactional, idempotent batch ingestion                                                        | Enforced                                    |
| Detect same-key payload mutation                                                                 | Enforced                                    |
| Reconcile Start/End response loss                                                                | Supported                                   |
| Accept ended-window recovery evidence                                                            | Enforced                                    |
| Freeze post-seal live evidence                                                                   | Enforced through quarantine                 |
| Block money until sealing                                                                        | Enforced                                    |
| Prove exact evidence completeness before sealing                                                 | **Not enforced**                            |
| Prevent grace-incomplete trips from automatic payout                                             | **Not enforced**                            |
| Avoid terminal rejection for an already-authorized trip solely because assignment status changed | **Not enforced**                            |
| Prevent duplicate initial payout rows                                                            | Strongly enforced at service/database level |

# Physical-device evidence still required

The repository itself marks physical validation as incomplete. `docs/adr/014-production-pwa-capability-contract.md:9-15,151-176`.

A release evidence package still needs:

1. Installed PWA tests on every claimed browser/device family, covering app switch, screen lock, unlock, browser minimization, and return to foreground.

2. OS-level location revocation while tracking, including whether the browser delivers a watch error immediately, only after the next fix, or only on foreground return.

3. Real wake-lock release under screen lock, low-power mode, thermal pressure, and browser suspension.

4. OS kill and reopen with unsent pending records, cut batches, retry attempts, and deadletter-only records.

5. Origin-storage pressure, eviction, manual site-data clearing, private-browsing behavior, quota exhaustion, and loss of the encryption-key record.

6. Two tabs or an installed PWA plus browser tab contending for the same Web Lock, including crash-release and reopen behavior.

7. Network fault injection at all three commit boundaries:

   * before the request leaves the browser;
   * after the database commit but before the response reaches the browser;
   * during End authority reconciliation.

8. Intermittent connectivity lasting longer than the seal grace period, with server logs proving which batches became live versus quarantined.

9. Device-clock changes and large skew while GPS positions are being recorded.

10. Concurrent seal workers and processing retries against a production-equivalent database, followed through the earnings ledger and any downstream disbursement integration.

No physical-device, live-GPS, or production payout claim is supported by this audit.

# Smallest remediation

The smallest safe release-unblocking set is targeted rather than a rewrite:

1. **Stop sealing on counts alone.** As an immediate guard, require:

   * `client_complete is true`;
   * `server_batch_count == client_batch_count`, not `>=`;
   * `server_ping_count == client_ping_count`.

   This is still not a complete trust boundary, but it immediately prevents the official client’s incomplete End from being treated as complete.

2. **Add a content-bound End commitment.** Retain a compact client receipt record for every cut batch—even after ACK—with at least its idempotency key and canonical payload hash. End should send either the ordered manifest or a verifiable root. Seal only after the server can match the exact committed set.

3. **Do not automatically pay `GRACE_EXPIRED` trips.** The smallest worker change is to block automatic money processing when `seal_reason == GRACE_EXPIRED`. Route these trips to an audited incomplete-evidence review. The resolution flow must permit valid quarantined evidence to be incorporated before the initial calculation, or the trip must remain ended rather than irreversibly sealed.

4. **Remove the assignment-deactivation terminal race.** Once a trip was validly started, continue accepting its bounded evidence regardless of subsequent assignment deactivation, while recording the deactivation for audit/fraud analysis. At minimum, `CAMPAIGN_ASSIGNMENT_NOT_ACTIVE` must remain retryable until End reconciliation rather than deadlettering the batch.

5. **Make deadletters durable and operable.** Include deadletter-only trip IDs in recovery discovery, display the affected batch and ping counts after reload, and provide an audited retry/export/review path. Do not silently reduce them to a diagnostics counter.

6. **Add four focused regression tests:**

   * incomplete End with a matching batch count must not seal;
   * grace-expired incomplete trip must not enter payout;
   * assignment deactivation before final drain must not strand the batch;
   * deadletter-only ended trip must remain discoverable after reload.

## Bottom line

**Offline evidence can be lost from the live trip and initial payout.** Ordinary response loss is handled safely, but finality is not tied to the exact evidence set, and valid batches can be deadlettered or quarantined.

**I found no code-confirmed path that automatically pays the same trip twice through the initial payout ledger.** The material financial risk at this revision is **partial or understated payment**, not duplicate initial payment.
