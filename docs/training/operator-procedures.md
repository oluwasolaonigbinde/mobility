# Operator procedures

These are provider-neutral teaching procedures. They summarize existing
runbooks and integrated entry points for a future facilitated session. Every
exercise uses synthetic identities and non-sensitive references; the source
runbook wins if a summary and its authority ever diverge.

Use the canonical placeholders in the handover
[role registry](../handover/roles-and-responsibilities.md#role-registry) until
the protected operating record contains approved named assignments. In
particular, `<INCIDENT_COMMANDER_ROLE>` remains distinct from
`<SECURITY_OWNER_ROLE>`. One active admin may perform the money actions through `<MONEY_OPERATOR_ROLE>` (D112); independent evidence and credential checks remain distinct. Never replace a
placeholder with a person, provider, account, domain, credential, or approval
inside the repository.

## Privacy / DSR

### Authorized role and entry point

Terrax staff handle personal-data requests manually under the separate decisions
of `<PRIVACY_DECISION_ROLE>`. D110 removed the in-app workflow. Follow the
[DSR runbook](../data-subject-request-runbook.md) and
[privacy operating model](../privacy-operating-model.md); an admin role is not
legal authority. No request endpoint or console is available.

### Prerequisites

- Use a synthetic subject and one protected, non-sensitive case reference.
- Confirm that no real personal-data processing or response wording is in
  scope; `EXT-LEGAL-PRIVACY` remains unresolved.
- Prepare six evidence-pointer locations: database, object storage, device
  queue, operational logs, backups, and processors. A pointer contains no
  personal values.

### Ordered actions

1. Record the request and received time in an approved protected operating record.
2. Verify the requester proportionately outside Cardvert; expose no identity evidence in Git.
3. Assess database records, private objects, devices, logs, backups and processors.
4. Obtain the lawyer's deadline, redaction and retention-exception rules before promising a response.
5. Record the actual action, remaining data, approved exceptions and safe response; never claim erasure without evidence.

### Retry identity

Keep the same protected case reference after response loss. Check actual store
state before repeating an action; do not fabricate an assessment or completion.

### Expected safe result

Each location has an honest evidence pointer or an unresolved stop. Immutable
money, fraud and audit facts remain unchanged. Legal rules remain MISSING.

### Stop conditions and escalation

Stop on unverifiable identity, unavailable/mismatched storage, unreachable
device, unknown log destination, missing backup manifest, unanswered processor,
remaining records after an erasure attempt, or an unapproved exception. Preserve
the case state and escalate the non-sensitive case reference to
`<PRIVACY_DECISION_ROLE>` and `<OPERATIONS_OWNER_ROLE>`; neither role may be
invented from this document.

### Synthetic rehearsal note

Use reserved synthetic identities and record counts only. Do not capture a
screenshot containing coordinates, identity data, object keys, or response
payloads. This note prepares an exercise; it records no executed DSR or adviser
decision.

## KYC and private files

### Authorized role and entry point

The driver/applicant supplies governed evidence; an active admin reviews it at
`/admin/driver-applications`. Sensitive reveal and retention remain purpose-
scoped admin API operations. Use the [KYC incident and retention runbook](../runbook.md)
and the shipped [KYC router](../../app/api/v1/kyc.py). Admin access is not blanket
permission to reveal NIN/bank values or download files.

### Prerequisites

- Use synthetic quarantined/clean files through the configured provider-neutral
  adapters; never use a real licence, NIN, bank account, or vehicle document.
- Confirm current scan status, private storage, active key version, submission
  state, and the operator's purpose before a reveal/review action.
- Treat retention as disabled until an approved positive policy is configured;
  a local test duration is not production authority.

### Ordered actions

1. Inspect the synthetic application and masked person/payee/vehicle state at
   `/admin/driver-applications`.
2. Open files only through the governed private-file action. A quarantined,
   changed, missing, or unavailable object remains blocked.
3. Approve or reject only the complete current submission. For any exceptional
   NIN reveal, call
   `POST /api/v1/admin/kyc/submissions/{submissionId}/nin/reveal` with an audited
   purpose; never copy the response.
4. For a future approved retention exercise, first call
   `POST /api/v1/admin/operations/file-kyc-retention` with `dry_run=true` and a
   protected approval reference. Reconcile eligible counts before any separate
   execution request.
5. After recovery, prove the same stored-file/submission IDs are clean and
   private; never edit scan/KYC status directly.

### Retry identity

File/submission creation retains its client request identity. A storage-delete
failure rolls back database changes and the retention operation is safe to
retry. Concurrent retention reports `lock_acquired=false`; wait for the holder,
inspect redacted audit counts, then retry normally if eligible items remain.

### Expected safe result

Only clean, current, privately stored synthetic evidence can advance its owning
workflow. Masked state stays readable during a key outage, but plaintext reveal,
new encryption, approval, and retention execution fail closed.

### Stop conditions and escalation

Stop on scanner timeout, storage outage/mismatch, key/authentication failure,
missing retention authority, concurrent run, incomplete documents, or any urge
to paste sensitive values into training evidence. Keep the object private and
escalate only environment, stored-file/submission identifiers, time window, and
error code to `<SECURITY_OWNER_ROLE>`, `<PRIVACY_DECISION_ROLE>`, and
`<OPERATIONS_OWNER_ROLE>`.

### Synthetic rehearsal note

Use generated non-identifying file content and placeholder identifiers such as
`<SYNTHETIC_SUBMISSION_ID>`. Exercise the dry-run boundary only; do not execute
destruction or treat local adapters as selected production providers.

## Fraud review

### Authorized role and entry point

An active admin reviews flags and replies to disputes at `/admin/fraud`. A
driver sees only the public reason/status and dispute path for their own trip at
`/driver/earnings/trips/{tripId}`. The [fraud API](../../app/api/v1/fraud_disputes.py)
preserves that projection boundary.

### Prerequisites

- Use a synthetic sealed trip with a current assessment and known non-sensitive
  flag identifier.
- Confirm the current flag transition, review deadline, dispute state, and money
  effect before acting.
- Assign the reviewing participant as admin and the affected participant as
  driver; neither may act through the other's session.

### Ordered actions

1. As driver, inspect the public hold reason and submit a bounded dispute if the
   UI offers it. Confirm internal evidence is absent.
2. As admin, filter `/admin/fraud`, inspect the current synthetic flag, public
   dispute, deadline, and displayed money effect.
3. Acknowledge only to record active review. Confirming fraud retains the
   governed hold/reversal behavior; dismissing removes the hold and still
   requires a current assessment before eligible earnings release.
4. Send a dispute reply through the shipped action without copying raw detection
   evidence into the message.
5. Reopen both role views and verify the public/admin projections agree on the
   transition without exposing internal evidence.

### Retry identity

Reload current state before repeating a transition or reply. Do not blind-submit
after response loss: a stale or conflicting transition must remain visible and
must not create a second money effect. Use the existing flag/dispute identity.

### Expected safe result

Open, acknowledged, and confirmed states keep affected money held according to
the current authority. An overdue unresolved case escalates and never
auto-releases. The driver receives only the public reason, status, notices, and
their dispute/reply.

### Stop conditions and escalation

Stop on stale assessment, unexpected status, tenant/driver mismatch, missing
evidence, duplicated reversal, changed money effect, or any proposed automatic
release. Preserve flag/dispute/trip identifiers and escalate to
`<MONEY_OPERATOR_ROLE>` and `<OPERATIONS_OWNER_ROLE>` without sharing raw route or
fraud evidence.

### Synthetic rehearsal note

Use a synthetic flag and driver. Compare role projections, transition ordering,
and hold behavior only; no allegation, physical check, payout consequence, or
operator decision involving a real person is recorded.

## Payout operations

### Authorized role and entry point

An active admin uses `/admin/money` and campaign pay settings. A driver reads only
their own ledger and breakdown at `/driver/earnings`. The shipped
[payout router](../../app/api/v1/payouts.py) and
[disbursement router](../../app/api/v1/disbursements.py) remain authoritative.
The prepared exercise uses `<MONEY_OPERATOR_ROLE>`; the same active admin may prepare, approve/apply and reconcile with reasons and audit (D112).

### Prerequisites

- Use synthetic sealed-trip calculations, immutable rule revisions, ledger
  entries, and a currency already present in the synthetic fixture.
- Confirm analytics/fraud authority is current; stale source fingerprints must
  fail instead of repricing history.
- Keep automated disbursement and settlement disabled until their provider,
  bank, custody, and approval gates are resolved outside this pack.

### Ordered actions

1. Inspect the calculation and ledger lineage at `/admin/money`; process only
   the documented synthetic trip when the current pipeline requires it.
2. Review the frozen campaign pay settings; never reprice accepted work.
3. Preview the exact correction and use Approve and apply with a reason. The same active admin may perform it; stale changes require a fresh review.
4. Reserve only eligible synthetic ledger entries. Use an audited add-only manual negative adjustment for an overpayment, on its actual Nigeria day (D113); no automatic debt recovery.
5. Stop before provider submission. A disabled adapter or missing live gate is
   the expected provider-neutral boundary, not an error to bypass.
6. As driver, confirm the own-ledger projection matches the governed state and
   exposes no admin controls or another driver's money.

### Retry identity

Reuse the existing calculation, correction-order, batch, and ledger identities.
After response loss, read current state before a transition. Retry only the
shipped idempotent action; never create a replacement row to hide uncertainty or
mark an instruction paid without its frozen provider receipt.

### Expected safe result

Synthetic money history remains conserved and append-only. Actors and reasons are recorded, stale calculations fail clearly, held money stays unavailable,
and the provider call count stays zero.

### Stop conditions and escalation

Stop on stale calculation, missing ledger lineage, missing actor/reason,
currency/value mismatch, unexplained adjustment, duplicate correction/reversal,
unresolved fraud hold, disabled provider, or missing settlement authority.
Preserve only synthetic IDs and expected/observed totals, then escalate to
`<MONEY_OPERATOR_ROLE>` and `<OPERATIONS_OWNER_ROLE>`.

### Synthetic rehearsal note

The provider-neutral acceptance path can be invoked from an appropriately
prepared repository environment:

Repository command: `python3 scripts/run_w403b_synthetic_journey.py`

The command's payout stage freezes an instruction without provider submission.
Its success is build evidence only; it is not a transfer, reconciliation, or
operator acceptance record.

## Reporting

### Authorized role and entry point

An authorized advertiser enters
`/advertiser/campaigns/{campaignId}/report` and the governed map at
`/advertiser/campaigns/{campaignId}/map`. Owner/manager membership may request
chosen-period reports for one or all owned campaigns; staff may re-run them
through the shipped [reports API](../../app/api/v1/campaign_reports.py). Use the
[governed report evidence](../pkg-08-w4-02a-governed-maps-report.md) and
[bounded issuance evidence](../pkg-08-w4-02b-bounded-issuance.md).

### Prerequisites

- Use an authorized synthetic tenant/campaign and complete retained data, or
  preserve the explicit unavailable/withheld result.
- Confirm the chosen Nigeria-day period, frozen snapshot hash, metric set and
  clearly labelled estimates. CSV has chart data and advert references; PDF has
  graphical charts and advert pictures. Absolute references use PUBLIC_ORIGIN.
- Live request/publication/download remains closed without approved privacy and
  report-method authority. A local schematic map is not a production basemap.

### Ordered actions

1. Open the synthetic Campaign Performance Analysis and distinguish verified
   operational results from clearly labelled modelled results.
2. Confirm reports contain no CTR, website visits beyond QR scans, ROI or financial figures (D115/D118).
3. Open the governed map; suppressed, stale, empty, inconsistent, or
   unauthorized output must mount no geometry.
4. As an authorized owner/manager advertiser, request the CSV/PDF pair. Persist
   the client request identity, poll the existing issuance, and withhold access
   until both private artifacts and hashes agree with the frozen report.
5. Retry a lost response with the same request identity. Create a new version
   only through staff's explicit append-only re-run action.
6. Verify cross-tenant, viewer, revoked-gate, partial-pair, tampered-object, and
   generic-file-route attempts remain denied without disclosing existence.

### Retry identity

An identical actor/request fingerprint replays one report. Changed facts with
the same identity conflict. Worker lease recovery and object writes converge on
the stored request; operators never fabricate completion or publish one member
of the pair.

### Expected safe result

The authorized synthetic participant sees one frozen, provenance-bearing
analysis and either a complete immutable CSV/PDF pair or an explicit unavailable
state. Raw routes, people, private URLs, hidden zones, and ROI remain
absent.

### Stop conditions and escalation

Stop on tenant/membership loss, missing/revoked privacy or method authority,
source mismatch, stale disclosure, unexpected ROI, partial/tampered
objects, worker/storage failure, or map-provider confusion. Preserve sanitized
run/issuance/request IDs and hashes, then escalate to
`<PRIVACY_DECISION_ROLE>`, `<REPORT_METHOD_AUTHORITY_ROLE>`,
`<MONEY_OPERATOR_ROLE>` when financial output is implicated, and
`<OPERATIONS_OWNER_ROLE>`.

### Synthetic rehearsal note

Use the same provider-neutral journey command listed in the payout section and
reserved `.invalid` synthetic identities. Do not call a live ad platform,
publish a real campaign report, or represent a synthetic estimate as
measured customer results.

## Incidents

### Authorized role and entry point

`<INCIDENT_COMMANDER_ROLE>` coordinates containment and recovery ordering;
`<SECURITY_OWNER_ROLE>` governs technical access and containment decisions,
and `<OPERATIONS_OWNER_ROLE>` receives operational escalation after that gate
is resolved. Follow
[release incident playbooks](../w4-03a-release-operations.md),
[privacy breach responsibilities](../privacy-operating-model.md), and the
[operations runbook](../runbook.md). No product UI declares an incident closed.

### Prerequisites

- Use a synthetic incident reference and a disposable/local rehearsal context.
- Record only affected revision, first/last event times, sanitized correlation
  IDs, impact class, containment, recovery checks, and role placeholders.
- Never include live payloads, request bodies, credentials, NIN/bank values,
  precise GPS, raw fraud evidence, object keys/manifests, presigned URLs, or
  backup plaintext.

### Ordered actions

1. Open the protected incident record and classify confidentiality, integrity,
   availability, misdirection, or unauthorized-processing impact without
   copying the payload.
2. Contain first: close/keep traffic closed, block the affected upload/report/
   payout/integration path, revoke affected access through the approved custody
   process, and preserve minimum sanitized evidence.
3. Select the matching playbook: credential rotation, worker backlog, migration
   failure, storage outage, report recovery, release recovery, or disaster
   restore. Do not downgrade schema, delete queues, expose storage, substitute
   local files, or manufacture success.
4. Recover through existing idempotent job/request/release identities. Run the
   documented readiness, canary, pair-agreement, or isolated-restore proof for
   the affected boundary.
5. `<PRIVACY_DECISION_ROLE>` decides any notification; this pack supplies no
   statutory deadline or legal conclusion.
6. Keep closure pending until recovery evidence, remaining impact, rotations,
   and follow-up role are recorded by authorized people in the protected system.

### Retry identity

Reuse the existing sanitized request/job/release/incident identities. Response
loss is reconciled by reading authoritative state. A conflicting retry, missing
completion marker, revision mismatch, or partial recovery keeps the affected
path stopped.

### Expected safe result

The exercise demonstrates a fail-closed containment and recovery decision tree
using synthetic facts. It does not notify anyone, rotate a live secret, switch
traffic, replace populated data, select a provider, or declare an incident
closed.

### Stop conditions and escalation

Stop on unknown release identity, missing owner/approver, possible data loss,
unverified backup/object agreement, schema mismatch, unredacted evidence,
unavailable custody, or any need to touch a live provider/account. Preserve the
minimum sanitized record and escalate to `<INCIDENT_COMMANDER_ROLE>`,
`<SECURITY_OWNER_ROLE>`, `<PRIVACY_DECISION_ROLE>`, `<MONEY_OPERATOR_ROLE>` when
money is implicated, and `<OPERATIONS_OWNER_ROLE>`.

### Synthetic rehearsal note

The bounded pilot journey includes a rejected fabricated-approval incident and
recovery while preserving the frozen receipt:

Repository command: `python3 scripts/run_w403b_synthetic_journey.py`

The heavier provider-neutral release/recovery rehearsal is available only on a
prepared disposable Docker host and was not run for this training-material
delivery:

Repository command: `bash scripts/rehearse_w403a.sh`

Neither command clears `EXT-RELEASE-ENV`, `EXT-STAGING-APPROVAL`, or
`EXT-OPERATIONS-OWNER`, and neither is facilitated user rehearsal or live
incident evidence.
