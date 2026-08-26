# Data-subject request runbook

This is the manual operator procedure for synthetic access, rectification and
erasure exercises. It does not authorize live personal-data processing. A
named active Cardvert administrator executes it; `EXT-LEGAL-PRIVACY` must
supply the accountable adviser, approved retention decisions, response text
and any exception references before a real request is handled.

## Safety rules

- Authenticate the requester proportionately outside Cardvert, then record
  only that verification occurred. Do not upload identity evidence into the
  case or paste personal data into an evidence reference.
- Use a unique client request UUID for every operator action. Repeating the
  exact action is safe; reusing its UUID with changed facts fails closed.
- Treat evidence references as non-sensitive pointers into the approved
  operations record. Never place names, email addresses, phone numbers,
  account numbers, object keys, raw locations or credentials in them.
- Do not mark a store complete from an assumption. An unavailable database or
  object store, an unreachable device, a missing backup manifest or an
  unanswered processor remains unassessed, so the case cannot complete.
- Never rewrite money, fraud or audit history. A retained-exception outcome is
  accepted only when its exact reference is present in
  `DSR_APPROVED_EXCEPTION_REFERENCES`. That setting is blank by default.
- Stop new collection or optional use before an erasure or withdrawal exercise.
  This runbook records the work; it does not itself supply legal authority.

## Case sequence

1. An active administrator opens the case through
   `POST /api/v1/admin/privacy/dsr-requests`, selecting `access`,
   `rectification` or `erasure` and recording the request time with timezone.
2. After the out-of-band identity check, the administrator calls
   `POST /api/v1/admin/privacy/dsr-requests/{request_id}/verify-identity`.
   Inventory and assessment remain blocked before this transition.
3. Call `GET /api/v1/admin/privacy/dsr-requests/{request_id}/inventory`.
   It counts the subject's database classes and managed-file metadata, and
   verifies every managed object against the private storage port. Missing,
   changed or unavailable objects fail the inventory closed.
4. Complete the location checks below. Record one immutable assessment per
   location with
   `POST /api/v1/admin/privacy/dsr-requests/{request_id}/locations/{location}`.
   Access uses `provided`/`not_found`, rectification uses
   `rectified`/`not_found`, and erasure uses `erased`/`not_found`. Use
   `retained_exception` only with an approved configured reference.
5. Call `POST /api/v1/admin/privacy/dsr-requests/{request_id}/complete` only
   after all six locations have evidence. The service refuses incomplete
   cases. Keep the response channel and wording outside this build until the
   privacy adviser approves them.

## Six-location check

| Location | Manual check and action | Required evidence |
| --- | --- | --- |
| `database` | Re-run the system inventory after the access export, approved field correction, erasure or exception decision. The inventory explicitly includes account/authentication, membership, driver/KYC/vehicle/installation, trip/raw/device-queue/derived/replay/impression, fraud/dispute, payout/financial, notification, audit and privacy-request classes. | Case-local pointer to the protected export/change record. Erasure cannot be recorded while any inventoried row remains; current immutable identity/money/audit/privacy-request links therefore require an approved exception, not a false deletion claim. |
| `object_storage` | Use the inventory endpoint so every subject-scoped managed object is checked through the provider-neutral private-storage port. For erasure, use the existing governed file-purge path, then re-run inventory. | Protected manifest/change pointer. Missing objects, metadata mismatch and storage outage stop the check. |
| `device_queue` | Ask the authenticated driver to stop tracking. For access, allow the encrypted durable queue to sync before exporting server records. For erasure, after the approved server decision, clear Cardvert site data in the browser and confirm the Cardvert queue database is absent before tracking resumes. Do not edit queued GPS in place; any discard/recapture correction requires the approved disposition and a recorded replacement action. | Device/session reference and non-sensitive before/after record count. No screenshot containing coordinates. |
| `operational_logs` | Search the approved bounded log/monitoring stores by the case's internal identifiers. Do not copy log bodies into the case. Remove only data the approved logging system permits; otherwise record the approved security exception. | Query/change record and per-class count. An outage or unknown log destination stays incomplete. |
| `backups` | Record the newest and oldest retained dump manifests and any approved encrypted off-host copies. `scripts/db_backup.sh` enforces both a maximum of 14 local dumps and a hard 1–35-day age bound. A DSR deletion ages out; backups are never edited in place. | Manifest reference, oldest backup time and affected-copy count. Off-host/provider copies must use the same or shorter bound. |
| `processors` | Send the approved request to every provider listed for the subject's purposes in `docs/privacy-register.json`. Keep every provider MISSING until selected and contracted. Record completion, zero records or an approved exception separately for each processor. | Provider ticket/receipt pointers and per-class total. An unanswered or unknown processor stays incomplete. |

For the four non-database locations, `external_record_count` is mandatory and
nonnegative. It is the operator-verified number of affected records represented
by the evidence pointer. A `not_found` outcome requires zero. Database and
object counts are computed by Cardvert and reject an operator-supplied count.

## Access, rectification and erasure dry runs

- **Access:** use a synthetic account, verify identity, produce a protected
  export outside the case, record `provided` for stores with data and
  `not_found` for empty stores, then complete. Confirm no personal value appears
  in audit metadata or the OpenAPI response beyond the subject UUID and counts.
- **Rectification:** change only the mutable source record through its owning
  domain workflow. Re-inventory, record the immutable correction pointer for
  every location, and do not rewrite historical ledger/audit evidence.
- **Erasure:** stop new tracking/optional processing first. Purge eligible files
  through the storage lifecycle, clear the device queue, propagate to logs,
  backups and processors, and re-inventory. If database records remain, the
  build refuses an `erased` assessment. Use `retained_exception` only for a
  configured synthetic test reference; production references require the
  missing legal decision.

## Evidence and failure recovery

Case identity, lifecycle transitions and location assessments are immutable in
both ORM and PostgreSQL. Exact concurrent retries converge; changed retries
conflict. A populated migration downgrade is refused so evidence is not
silently lost. If any action fails, leave the case at `identity_verified`, fix
the affected system, and retry with the same client request UUID only when the
facts are identical.
