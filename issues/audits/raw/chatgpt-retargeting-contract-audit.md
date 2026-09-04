---
source_surface: ChatGPT
project: TSS
conversation_id: 6a969018-fd90-83ea-b8ce-fa39b76c0dbc
displayed_title: Retargeting Contract Audit
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Retargeting Contract Audit

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Offline-to-online retargeting red-team audit

## Revision and audit basis

The requested branch was verified through GitHub. `feat/pkg-04-build-first` resolves to exactly:

`637841d95493bcc24334356da42097fa53a5d16f`

The commit was created on August 28, 2026, with tree `3751f22346eae91a9916eeb41d8a8b51b63254ba`. I did not substitute `master`.

This was a read-only, exact-revision static review through connected GitHub file access. Terminal git/DNS access was unavailable, so I did not execute the focused tests or a full suite. GitHub reports no Actions runs and no attached status contexts for this commit; therefore, the “passing” statements in `docs/progress.md` are repository claims, not independently executed evidence in this audit.

No advertising platform or other external provider was contacted.

# Verdict

## **PARTIAL IMPLEMENTATION — the complete contract is not implemented**

Cardvert has a substantial provider-neutral foundation:

* Five closed, aggregate-only planning-source types.
* Tenant-scoped campaign/target-zone/window links with frozen parent fingerprints.
* Immutable measurement-run and exposure-score provenance.
* An append-only exposure-segment container.
* Distinct-vehicle suppression.
* Aggregate recommendations.
* A controlled CSV format.
* An admin-only, test-only synthetic activation seam.
* A production fail-closed adapter boundary.

However, the most important bridge in the requested chain is missing:

> **Exposure-segment cells are supplied as job input; they are not derived by the system from the bound offline vehicle exposure.**

The immutable hashes therefore prove which aggregate claim was stored, not that its cells, vehicle counts, trip counts, geography, time buckets, or contact estimates came from the immutable measurement run.

There are also release-blocking issues for any future live delivery:

1. Spatial and temporal coarseness are not enforced.
2. Audience releases do not participate in the existing anti-differencing history.
3. Export and activation have no action-level purpose or approval authority.
4. Activation is not crash-safe or semantically exactly-once.
5. The source model has no way to bind a legal approval to a formerly “unapproved” source.

The current defaults prevent live provider activation, so these defects do **not** describe a presently enabled Meta, Google, or TikTok leak. They mean that merely supplying the missing external credentials and approvals would still not be sufficient for safe live activation.

## Explicit answer

> **Is offline-to-online retargeting implemented? — No, not end-to-end and not as a live targeting capability.**

What is implemented is an aggregate planning/reporting/export foundation plus synthetic activation testing. It generates targeting-shaped recommendations and CSV rows, so it is more than static reporting, but it does not authoritatively derive those targets from offline exposure and cannot activate a real advertising platform.

# End-to-end data-flow map

```text
1. Advertiser records typed planning metadata
   website / digital campaign / CRM reference / UTM / manual insight
                               │
                               ▼
2. Source is linked to organization + campaign + target zone + time window
   Parent snapshots and fingerprints are frozen
                               │
                               ▼
3. Measurement run freezes derived operational facts
   TripAnalytics + authoritative ImpressionEstimate + payout/proof evidence
                               │
                               ▼
4. EXPECTED: compute geo × time exposure cells from those frozen facts
   ACTUAL: ARQ job receives caller-supplied `cells`
                    ───────────╳───────────
                               │
                               ▼
5. Supplied cells are schema-checked, k-filtered and frozen as a segment
   Exact replay converges; changed facts create a reissue
                               │
                     ┌─────────┴─────────┐
                     ▼                   ▼
6a. Recommendations             6b. Controlled CSV
    cell + time + context            cell + time + context
                     │
                     ▼
7. Admin activation API
   Synthetic fake adapter only in test mode
                               │
                               ▼
8. Real Meta / Google / TikTok adapter
   NOT IMPLEMENTED; builder always returns disabled adapter
```

The architecture explicitly requires worker materialization “from analytics aggregates” and allows only aggregate geography, time, and context downstream. `docs/architecture.md:1829-1859, 1924-1932`.

# Confirmed privacy, security and semantic defects

## 1. High — the offline-exposure-to-segment bridge trusts supplied aggregate claims

The worker contract takes three inputs: a measurement-run ID, source-link ID, and an arbitrary list of cell dictionaries:

* `app/jobs/exposure_segments.py:9-25`
* `app/services/audience.py:911-920`

The service validates that the run and link belong to the same tenant and campaign and that the run reproduces. It then normalizes the supplied cells and hashes them into the segment facts:

* `app/services/audience.py:928-999`
* `app/services/audience.py:1006-1066`

It does **not** query authoritative cell aggregates or establish that:

* A cell was traversed by any vehicle in the run.
* The cell intersects the linked target zone.
* `distinct_vehicle_count` equals a server-computed distinct count.
* `trip_count` reconciles to the run.
* `modelled_potential_contacts` reconciles to the measurement result.
* The sum of cells conserves any run-level total.

The disclosure floor is applied to the supplied `distinct_vehicle_count`:

* `app/services/audience.py:1071-1077`

The focused tests likewise construct cell dictionaries by hand and submit them to the service and worker:

* `tests/test_exposure_segments.py:34-55`

* `tests/test_exposure_segments.py:137-190`

### Break case

Given any valid link, reproducible measurement run and exposure score, an internal queue producer can submit:

```text
coverage_cell: grid-500m:999999:999999
distinct_vehicle_count: 10000
trip_count: 10000
modelled_potential_contacts: 999999999
```

provided the time window is within the link and run periods. The cell can be unrelated to the target zone and unsupported by the measurement run. It passes the k-floor because the asserted count is high enough.

There is no public HTTP materialization route in the inspected tree, which limits the immediate attack surface to internal job production or queue compromise. But it also means no legitimate end-to-end producer exists: the feature stops at an internal aggregate assertion boundary.

**Consequence:** the implementation cannot truthfully claim “offline vehicle exposure → governed aggregate segment.”

---

## 2. High — spatial and temporal coarseness are not enforced

`ExposureCellInput` accepts any positive grid resolution:

```python
r"^grid-[1-9][0-9]*m:-?[0-9]+:-?[0-9]+$"
```

It also accepts any timezone-aware interval where `start < end`:

* `app/schemas/exposure_segments.py:8-32`

The outbound adapter schema repeats the same permissive cell pattern and interval rule:

* `app/schemas/audience_delivery.py:12-37`

Yet settings define a central minimum spatial resolution, currently `privacy_min_resolution_m = 500`:

* `app/core/config.py:207-230`

No audience materialization or delivery function parses the resolution or enforces that setting. No minimum bucket duration or canonical bucket alignment exists. The materializer only verifies that the supplied interval falls inside the link and run periods.

### Break case

A valid cell may be submitted as:

```text
grid-1m:123456:987654
2026-08-01T12:00:00.000000Z
2026-08-01T12:00:00.000001Z
```

with an asserted distinct-vehicle count above k.

That record is still technically “geography/time/context only,” but it can represent near-route-level spatial and temporal precision. The CSV serializes the exact timestamps without rounding.

This contradicts the architecture’s coarse-cell boundary and its statement that precise timestamps must not appear in audience outputs: `docs/architecture.md:1863-1898`.

The k-floor alone does not fix this. “Three vehicles were in this one-metre cell during this microsecond interval” is not an acceptably governed aggregate.

---

## 3. High for live activation — submission is neither crash-safe nor semantically exactly-once

Normal same-key replay is implemented and tested. The service takes a PostgreSQL advisory lock, checks for a receipt, and uses a deterministic delivery UUID as the adapter idempotency key.

But the external ordering is unsafe:

1. The adapter is called.
2. It may successfully accept the operation.
3. Only afterwards is the `AudienceDelivery` row created.
4. The audit event is then created.
5. The API route later commits the transaction.

Relevant code:

* Adapter call: `app/services/audience_delivery.py:602-616`
* Delivery row and audit creation: `app/services/audience_delivery.py:617-638`
* API commit: `app/api/v1/audience_delivery.py:128-158`

The delivery model permits only `status = 'completed'`; it has no `prepared`, `submitting`, `unknown`, `failed`, or reconciliation state:

* `app/models/audience_delivery.py:20-45, 77-90`

### Crash break case

A real provider accepts the request and returns a provider reference. The process then dies before the database commit. On retry:

* There is no receipt.
* There is no durable attempt.
* There is no unknown-outcome state to reconcile.
* The adapter is invoked again.

The deterministic provider key helps only if every future adapter and provider gives a documented, queryable idempotency guarantee. That guarantee is absent from the adapter protocol and persistence model.

### Different-key/concurrent break case

The database uniqueness rule is:

```text
(actor_user_id, operation, idempotency_key)
```

It is not a semantic activation identity such as:

```text
(segment snapshot, provider account, purpose, approval, activation generation)
```

Therefore:

* The same admin can use two different keys.
* Two admins can use different keys.
* Both requests can activate the same segment.
* Both generate different delivery IDs and provider idempotency keys.
* Both are accepted as distinct operations.

The focused concurrency test covers the same admin and the same key only:

* `tests/test_audience_delivery.py:512-588`

This is especially important for ad platforms because a duplicate activation may create duplicate campaigns, ad sets, or spend rather than merely duplicate a harmless read.

Current live safety is preserved because the production adapter is disabled and non-synthetic adapters are rejected before invocation.

---

## 4. Medium — exports and activations are audited but not purpose-scoped or approved

The architecture says every export or push must be “purpose-scoped, approved and audited”: `docs/architecture.md:1847-1859`.

Only the auditing portion exists.

`AudienceDeliveryRequest` is an empty, closed body:

* `app/schemas/audience_delivery.py:8-10`

It has no:

* Purpose code.
* Approval ID.
* Approval expiry.
* Approved operation type.
* Approved provider/account.
* Approved segment or payload hash.
* Legal-basis evidence.
* Budget authority.

The service checks role, tenant, staleness and disclosure floor, but no action-level approval:

* `app/services/audience_delivery.py:442-638`
* `app/api/v1/audience_delivery.py:100-158`

Furthermore, every planning source can only have:

```text
lawful_basis_status = unapproved
consent_disclaimer_status = not-reviewed
```

There is no source-approval transition:

* `app/schemas/retargeting_sources.py:12-25`

The central live gate validates global configuration references, not source- or action-specific authority:

* `app/services/disclosure.py:51-75`

### Consequence

If the global privacy settings were enabled after legal review, the application would still have no machine-enforced evidence that a particular source, segment, CSV export, or platform push was approved for a named purpose.

A global legal reference is not a substitute for the architecture’s per-delivery approval contract.

---

## 5. Medium — audience releases bypass the existing anti-differencing history

The disclosure service has a fixed route inventory for eight older analytics/report/heatmap surfaces:

* `app/services/disclosure.py:17-29`

No recommendation, exposure-segment export, or activation route is registered.

The only spatial release-history function is explicitly heatmap-only and rejects any other route:

* `app/services/disclosure.py:149-238`

The audience service imports the global gate and k-floor but not the disclosure-history recorder:

* `app/services/audience.py:43-49`

### Break case

An advertiser can define overlapping source links, for example:

```text
A: zone Z, 09:00–10:00
B: zone Z, 09:00–09:30
C: zone Z, 09:30–10:00
```

If authoritative segments were eventually generated for each link, the advertiser could compare which cells appear or disappear across the complementary releases. This can reveal threshold-crossing information even though each individual release passes k.

The existing heatmap control serializes and suppresses overlapping spatial queries specifically to prevent this style of differencing. Audience recommendations and CSV exports do not use it.

The risk is currently latent because live Module G output remains externally gated and the segment derivation itself is missing. It must be closed before enabling real data.

---

## 6. Low/medium — planning-source UI retries do not preserve idempotency keys

The backend idempotency mechanisms work only when the caller reuses the same key. The frontend server actions mint a fresh `randomUUID()` every time an action executes:

* Source creation: `frontend/src/app/advertiser/planning-sources/actions.ts:70-76`
* Source deactivation: `:84-93`
* Link creation: `:114-127`
* Link removal: `:136-145`

### Break case

A source creation commits successfully, but the browser loses the response. A user retries. The new server-action execution generates a different key, so the backend sees a new operation and may create a duplicate source.

For link creation, deactivation and removal, the retry may instead surface an “already exists/not active” conflict rather than replaying the successful response.

The CSV BFF does better: it uses a stable segment-derived export key at `frontend/src/app/api/advertiser/exposure-segments/[segmentId]/export/route.ts:7-20`.

---

## 7. Low — one UI claim is stronger than its enforcement

The link form says:

> “Only owned active sources, campaigns and target zones are accepted.”

`frontend/src/app/advertiser/planning-sources/link-form.tsx:108-113`.

The page filters sources to active ones, but it passes every campaign returned by the campaign listing without a campaign-status filter:

* `frontend/src/app/advertiser/planning-sources/page.tsx:22-31`
* `frontend/src/app/advertiser/planning-sources/page.tsx:226-239`

The service validates ownership, source activity/expiry, target-zone type and date compatibility, but does not define an allowed campaign-status set.

This may be a copy defect rather than a backend defect—historical or completed campaigns may legitimately be used for follow-up analysis. The smallest correction is to define the intended status policy and then either enforce it or narrow the wording.

# Requirement coverage matrix

|  # | Requirement                                                  | Status                                 | Exact evidence and conclusion                                                                                                                                                                                                                         |
| -: | ------------------------------------------------------------ | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|  1 | Five allowlisted source types                                | **PASS**                               | Exactly `website-traffic`, `digital-campaign-audience`, `CRM-upload-reference`, `UTM-source`, and `manual-insight`; discriminated union at `app/schemas/retargeting_sources.py:25-67`.                                                                |
|  2 | Reject URLs, identifiers, uploads, notes and opaque metadata | **PASS**                               | `extra="forbid"` on all source variants and read snapshots; focused rejection cases at `tests/test_retargeting_sources.py:25-82`.                                                                                                                     |
|  3 | Source expiry/deactivation/correction                        | **PASS with provenance caveat**        | DB-clock expiry and immutable deactivation event exist. Correction is deactivate-plus-new rather than mutation. There is no explicit `supersedes_source_id` linking the replacement to the old source.                                                |
|  4 | Tenant/campaign/zone/window compatibility                    | **PASS for defined rules**             | Active tenant membership, source tenant/expiry, campaign ownership, target-zone type, campaign bounds and source expiry are checked in `app/services/audience.py:580-735`. Campaign lifecycle status is not part of the defined service policy.       |
|  5 | Parent drift and stale segments                              | **PASS**                               | Source/campaign/zone fingerprints and source activity are recomputed at `app/services/audience.py:878-899`; segments additionally recheck measurement hashes and reproducibility at `:1156-1173`.                                                     |
|  6 | Distinct-vehicle disclosure floors                           | **PARTIAL**                            | Applied before persistence and re-applied before output. However, the distinct count itself is supplied by the job caller rather than authoritatively computed.                                                                                       |
|  7 | Raw-ping and route-data access                               | **PASS at audience boundary**          | `app/services/audience.py:1-49` imports no ping or trip-session model. The measurement run uses derived `TripAnalytics` and authoritative `ImpressionEstimate` rows, joined to sessions for period scoping, at `app/services/measurement.py:341-385`. |
|  8 | Geography/time/context-only output                           | **FAIL on granularity**                | Field allowlist passes, but `grid-1m` and arbitrarily short intervals are valid. Existing minimum spatial resolution is not enforced.                                                                                                                 |
|  9 | No driver, trip, device, phone, account or person IDs        | **PASS outbound**                      | Source, cell, recommendation, CSV and activation schemas exclude these fields. Focused tests reject them at `tests/test_exposure_segments.py:57-75` and `tests/test_audience_delivery.py:337-373`.                                                    |
| 10 | Free-form payload smuggling                                  | **PASS**                               | Closed Pydantic schemas, literal fields, constrained cell string, and empty delivery request with `extra="forbid"`.                                                                                                                                   |
| 11 | Controlled CSV behavior                                      | **PARTIAL**                            | Fixed columns, fixed filename, `csv.DictWriter`, no-store response and content hash are good. Missing purpose approval, granularity controls and anti-differencing history prevent a complete governance pass.                                        |
| 12 | Admin-only activation                                        | **PASS**                               | Admin dependency at `app/api/v1/audience_delivery.py:128-158`, plus service-level active-admin check. The test verifies advertisers receive 403.                                                                                                      |
| 13 | Retry, replay and concurrency                                | **PARTIAL**                            | Same actor/key replay and same-key PostgreSQL concurrency converge. Different keys/actors can duplicate activation; provider-success/DB-crash is unresolved; frontend planning actions regenerate keys.                                               |
| 14 | Synthetic-adapter isolation                                  | **PASS**                               | Fake adapter requires test environment, synthetic disclosure mode, enabled and `synthetic=True`; API dependency normally supplies the disabled adapter.                                                                                               |
| 15 | Live-adapter fail-closed behavior                            | **PASS**                               | Any non-synthetic adapter is rejected before invocation; the trap adapter test proves it is not called at `tests/test_audience_delivery.py:421-450`.                                                                                                  |
| 16 | Audit receipts and provenance                                | **PARTIAL**                            | Source/link histories, segment hashes, run/proof hashes, delivery receipts and audit events exist. Missing durable activation attempts/unknown outcomes and action-level approval provenance.                                                         |
| 17 | Advertiser/admin UI claims                                   | **PARTIAL**                            | Aggregate-only, uncertainty, controlled CSV and disabled activation claims are generally accurate. The “active campaigns” link-form statement is not enforced.                                                                                        |
| 18 | Targeting or only reporting                                  | **SYNTHETIC TARGETING FOUNDATION**     | Recommendations and targeting CSV go beyond ordinary reporting, and a fake adapter accepts the same payload. No real platform targeting occurs.                                                                                                       |
| 19 | Person-level retargeting outside pilot                       | **PASS**                               | D20/Q11 explicitly keeps it outside the pilot and requires later lawful identity data, approval and an approved partner. `docs/decisions-log.md:42-44, 95-99`.                                                                                        |
| 20 | Real Meta/Google/TikTok activation                           | **NOT IMPLEMENTED / EXTERNALLY GATED** | No concrete adapter, account mapping, credentials, API access, budget, provider reconciliation or action approval. Builder remains disabled.                                                                                                          |

# What works synthetically

The following mechanisms are credibly implemented in source:

* **Planning-source registry:** all five source kinds, closed typed fields, expiry, deactivation, retry identity, append-only history and tenant isolation.
* **Source links:** organization/campaign/target-zone/window validation, frozen source/campaign/zone fingerprints, immutable create/remove history and parent-staleness detection.
* **Measurement provenance:** immutable runs bind derived analytics, authoritative impressions, payout facts, proof evidence and result hashes. Internal manifests may retain trip/assignment IDs, but these are not included in outbound targeting payloads.
* **Segment container:** append-only versions, exact replay, changed-fact reissue, stale-parent handling, pre-persistence k suppression and current-floor rechecking.
* **Recommendations:** deterministic aggregate geography/time recommendations with measurement and segment hashes plus uncertainty/disclaimer text.
* **CSV shape:** only campaign UUID, coverage cell, start time, end time and fixed `vehicle_transit` context.
* **Synthetic activation:** a fake adapter can be injected only in test mode; same-key replay and same-key concurrency converge.
* **Live fail-closed behavior:** the default adapter is disabled, and a non-synthetic adapter is rejected before invocation.

The focused tests are meaningful contract examples, but they were not executed in this audit and no CI run is attached to the audited commit.

# Advertiser and admin UI assessment

## Advertiser UI

The advertiser surface accurately describes the inputs as “Aggregate-only retargeting inputs,” exposes the five source choices, and states that identifiers, uploads, URLs and notes are rejected:

* `frontend/src/app/advertiser/planning-sources/source-form.tsx:24-31, 117-120`
* `frontend/src/app/advertiser/planning-sources/page.tsx:50-56`

Recommendations are explicitly described as aggregate geography/time recommendations. Stale and suppressed states are visible, the download is labelled “controlled CSV,” and evidence hashes plus uncertainty/disclaimer text are shown:

* `frontend/src/app/advertiser/planning-sources/page.tsx:155-204`

There is no advertiser activation control.

## Admin UI

The admin surface is read-only monitoring. It labels the page “Campaign analysis governance,” shows source/link status and recommendation state, and explicitly states:

* Live use awaits legal/privacy and report-method approval.
* Ad-platform activation remains disabled while `EXT-AD-PLATFORM` is missing.

`frontend/src/app/admin/planning-sources/page.tsx:44-48, 210-217`.

The UI therefore does not overclaim live provider targeting.

# What remains externally gated

The repository correctly records these missing external authorities:

* `EXT-LEGAL-PRIVACY`

  * Named legal/compliance approval.
  * Approved purposes and lawful bases.
  * Consent/notice wording.
  * Retention and DSR decisions.
  * Approved disclosure thresholds and history-retention policy.
* `EXT-REPORT-METHOD`

  * Approved live measurement/report methodology and revision.
* `EXT-AD-PLATFORM`

  * Selected provider or providers.
  * Named client-owned accounts and ad-account IDs.
  * API access and application approval.
  * Credentials and refresh/rotation arrangements.
  * Approved activation budget.

The §35 `G-moduleG` gate blocks live retargeting ingestion, display and export while privacy/reporting gates remain unresolved. `docs/architecture.md:2600-2620`.

## External inputs alone are not enough

Even after those facts are supplied, real activation still requires code work:

1. **Provider-specific resource mapping**

   * Internal campaign → provider account, campaign/ad group/ad set, creative and objective.
   * Approved budget and schedule.
   * Provider-supported geography conversion from Cardvert cells.

2. **Concrete adapters**

   * Separate Meta, Google and/or TikTok implementations behind the existing port.
   * Explicit rejection of customer-list, hashed-email, mobile-ad-ID or person-level modes.

3. **Credential custody**

   * Secret storage, token rotation, revocation and least-privilege scopes.

4. **Purpose and approval authority**

   * Immutable approval covering segment hash, operation, provider/account, purpose, budget and expiry.

5. **Crash-safe submission**

   * Durable activation intent before the network call.
   * Provider idempotency and lookup/reconciliation.
   * Unknown-outcome recovery.

6. **Provider result convergence**

   * Submission receipt.
   * Polling/webhook reconciliation.
   * Rejected, paused, completed and cancelled states.
   * Provider-side identifiers and immutable response hashes.

7. **Operational proof**

   * Sandbox/provider-test-account evidence.
   * Rate-limit and outage behavior.
   * Credential-expiry and permission-revocation tests.
   * Approved staging rehearsal without person-level data.

Person-level custom audiences remain outside the pilot. Supporting them later would be a separate product and legal decision requiring lawfully obtained identity data, an approved identity/location-data partner and an entirely separate data contract—not an extension of the current aggregate payload.

# Smallest remediation for the confirmed issues

## 1. Make the segment job derive facts rather than receive them

Change the ARQ signature from:

```python
materialize_exposure_segment_job(
    measurement_run_id,
    source_link_id,
    cells,
)
```

to:

```python
materialize_exposure_segment_job(
    measurement_run_id,
    source_link_id,
)
```

Introduce one formula-versioned authoritative exposure-cell aggregate produced by the analytics pipeline. The audience worker should read that aggregate using the exact run/link authority and calculate distinct vehicles server-side.

Before issuance, require:

* Cell belongs to or intersects the frozen linked target zone.
* Cell time bucket is within the run/link.
* Resolution is at least `privacy_min_resolution_m`.
* Time bucket follows an approved configured duration and alignment.
* Vehicle/trip/contact totals reconcile to the authoritative inputs.
* Formula version and derivation fingerprint are frozen.

The materializer should never accept vehicle counts or contact estimates from an ARQ payload.

## 2. Enforce spatial and temporal disclosure policy

Parse `coverage_cell` into structured resolution and indices rather than treating it as one opaque string.

Reject:

* Resolution below the approved minimum.
* Noncanonical grid alignment.
* Unsupported coordinate systems.
* Windows shorter than the approved bucket.
* Unaligned or overlapping cells within one segment.

Production should fail closed if no approved time-bucket policy is configured; do not invent a live default.

## 3. Put audience outputs into disclosure history

Generalize the heatmap-specific recorder into a spatial-output recorder and register at least:

* Advertiser recommendations.
* Admin recommendations where relevant.
* CSV exports.
* Activation payload issuance.

Bind the history decision to:

* Principal.
* Organization.
* Campaign.
* Link and segment snapshot hashes.
* Geography.
* Time interval.
* Operation/purpose.
* Result hash.

Suppress complementary or overlapping releases under the approved policy.

## 4. Add an immutable delivery approval authority

Add a closed approval record that binds:

* Organization and campaign.
* Exact source/link/segment hashes.
* Purpose code.
* Allowed operation: CSV or named provider activation.
* Provider account where applicable.
* Budget ceiling.
* Legal/reference evidence.
* Approver.
* Validity period.

Require it in `AudienceDeliveryRequest` and store its immutable snapshot/hash in every delivery receipt and audit event.

A separate source-approval event or approval record should move a source from candidate metadata to legally usable authority without rewriting the source snapshot.

## 5. Make activation intent durable and semantically unique

Before calling a provider:

1. Create and commit an immutable activation intent.
2. Give it a semantic identity based on segment hash, provider account, purpose/approval and activation generation.
3. Submit through a worker using that intent’s stable provider idempotency key.
4. Append attempt and outcome events.
5. On timeout or crash, mark/retain `unknown` and query the provider rather than blindly resubmitting.
6. Materialize the completed immutable delivery receipt only after reconciliation.

Add a crash-injection test that raises immediately after fake-provider acceptance and proves that retry produces one provider-side effect and one reconciled completion.

## 6. Stabilize UI request identities

Generate each planning-action idempotency key once in the client/form state and reuse it through lost responses and retries. Do not generate it afresh in the server action.

For deactivation and removal, a deterministic actor/resource/operation key is sufficient because the payload is fixed.

## 7. Correct the campaign-status wording

Either:

* Define and enforce an explicit campaign-status allowlist in the service and UI; or
* Change the copy to say “active source, owned campaign and target zone” if historical/completed campaigns are intentionally eligible for post-campaign follow-up analysis.

# Required focused regression cases

The smallest verification set should include:

1. The materialization job no longer accepts `cells`.
2. A forged vehicle count cannot enter a segment.
3. A cell outside the frozen target zone is rejected.
4. Cell/contact totals must reconcile to authoritative analytics.
5. `grid-1m` is rejected under a 500-metre policy.
6. A one-second or unaligned interval is rejected.
7. Complementary overlapping exports are suppressed.
8. An unapproved purpose/source cannot be exported or activated.
9. Two admins using different request keys cannot accidentally perform the same semantic activation twice.
10. Provider success followed by process death converges without resubmission.
11. Provider timeout creates an inspectable unknown outcome.
12. A lost frontend response reuses the original idempotency key.
13. Non-synthetic adapters remain unreachable until the complete live gate is present.
14. Person-level fields remain rejected at every source, segment, delivery and adapter boundary.

The current code is a credible synthetic foundation, but the authoritative exposure derivation and real-delivery safety contracts must be added before Cardvert can truthfully describe the feature as implemented offline-to-online retargeting.
