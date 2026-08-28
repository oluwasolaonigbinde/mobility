# W4-03A provider-neutral release operations

Status: **repository preparation only**. This runbook does not authorize an
external deployment. `EXT-RELEASE-ENV` is still missing and
`DV-STAGING-LIVE` is still `NOT RUN — EXT-STAGING-APPROVAL`; W4-03A therefore
remains open.

## Authority and protected inputs

Run every command from the repository root. The approved operator supplies,
outside the repository:

- `EXT-RELEASE-ENV`: client-owned account, domain, provider, budget, and
  access; this is also the authority for DNS, registry, secret store, private
  database, private versioned object storage, and encrypted off-host backup
  destination choices;
- `EXT-STAGING-APPROVAL`: approval to incur external staging spend and perform
  the live rehearsal;
- `EXT-OPERATIONS-OWNER`: the named incident commander/receiving operator;
- an environment file based on `production.env.example`, a mode-0600 backup
  passphrase file, a mode-0600 smoke-password file, and compatibility evidence
  for the previous image against the forward-migrated schema.

Do not put any of those files in the checkout, image, release log, command
line, ticket, or evidence document. The environment example is deliberately
invalid: placeholders, mutable images, weak secrets, unsafe origins, public
service ports, development switches, or unreviewed client-IP trust all fail
preflight.

## External run sheet

The future approved account/domain run is deliberately short:

1. Record `EXT-RELEASE-ENV`, `EXT-STAGING-APPROVAL`, and the named
   `EXT-OPERATIONS-OWNER`. Confirm private PostGIS, Redis/broker and versioned
   object storage; expose only the Caddy TLS edge.
2. Build backend/frontend from one reviewed Git revision, pass that full
   revision as `VCS_REF`, use the reviewed hash-locked
   `requirements-production.txt` and frontend lockfile, publish immutable
   digest references, and obtain the five exact application/infrastructure
   image digests.
3. Create the protected production environment and credential files outside
   the checkout. Keep live issuance and synthetic/test switches false.
4. Validate configuration and exact image labels:

   ```bash
   python3 scripts/release_contract.py preflight \
     --env-file /secure/cardvert-production.env \
     --compose-file docker-compose.production.yml --check-images
   ```

5. Validate DNS/TLS and Caddy, confirm that only edge ports 80/443 are public,
   and confirm the backup destination is encrypted and off host.
6. Execute the deterministic release with protected state, backup, smoke
   credentials, and compatibility evidence:

   ```bash
  scripts/release.sh \
     --env-file /secure/cardvert-production.env \
     --state-dir /secure/cardvert-release-state \
     --backup-dir /secure/off-host-cardvert-backups \
     --smoke-email approved-smoke-account \
     --smoke-password-file /secure/cardvert-smoke-password \
     --compatibility-evidence /secure/previous-image-compatibility.json
   ```

   Compatibility evidence is machine-read JSON. For a rollout with a
   predecessor it contains exactly the target release ID/revision/backend
   digest, previous release ID/revision/backend digest, forward Alembic
   revision, `result: "passed"`, and these true checks:
   `no_database_downgrade`, `previous_image_readiness`, and
   `previous_image_report_schema_canary`. A first release uses null previous
   fields and true `first_release_no_predecessor` plus
   `no_database_downgrade`. The validator rejects a prose note or a digest that
   does not match the selected releases.

7. Copy the encrypted bundle, digest, and complete marker off host. Run
   `scripts/verify_restore.sh` against the bundle. It restores an isolated
   database and temporary object prefix; it never switches traffic.
8. Capture `DV-STAGING-LIVE`: public TLS/HSTS and edge allowlist, exact
   revision/image/config state, migration head/PostGIS, worker/broker/storage
   readiness, authenticated smoke, backup marker/manifest, isolated restore,
   previous-image recovery, and cleanup. Redact every credential, person,
   private URL, bank/KYC value, precise location, and fraud artifact.

Do not mark W4-03A complete until those live steps pass in the approved
client-owned environment.

## Deterministic deploy and retry contract

`scripts/release.sh` owns the ordered state machine `preflight → backup →
migration → compatibility → traffic`. State lives outside the repository with
mode 0600, binds release ID, Git revision, immutable backend/frontend images,
rendered-config digest and previous release ID, and advances only by a
consecutive stage. A retry with the same authority resumes completed stages; a
different authority conflicts. A second release cannot enter while the lock
exists. `--recover-stale-lock` is permitted only after incident review and a
`stale-lock-recovery.reference` has been placed in the protected state
directory.

The release host pulls images and always uses `--no-build`. The edge stops
before migration. A lost migration response is reconciled only when the
database exactly matches the image's single Alembic head. Readiness then proves
database revision/PostGIS, Redis, worker heartbeat and object
write/read/delete; a report-schema canary and the externally supplied
compatibility evidence precede the traffic switch. Any failure leaves traffic
stopped and reports only the failed stage.

## Recovery, never downgrade

Application recovery uses `scripts/recover_release.sh` with the current state,
the exact previous environment, smoke credentials, and previous-image
compatibility evidence. The previous release ID must match the current state's
recorded authority. The clean recovery-orchestrator checkout must still match
the failed current state's revision while previous image labels match the
previous environment. Recovery stops all writers, starts the previous
immutable images against the forward-migrated database, proves readiness, then
reopens the edge and records a private evidence file.

It never runs `alembic downgrade`, destructive SQL, or an automatic database
restore. If the previous image is not proven compatible, keep traffic stopped
and escalate to the incident owner. Data restore is a separately approved
disaster-recovery action.

## Encrypted backup and isolated restore

`scripts/backup_release.sh` stops edge/frontend/API/worker writers, records the
running set, takes a custom-format database dump with Alembic/PostGIS/WAL-time
marker evidence, and snapshots every database-authorized private object with
version ID, byte count and SHA-256. It creates a canonical authenticated
manifest tied to release/config/revision, encrypts the exact four-member bundle
with AES-256, writes ciphertext digest and complete marker atomically, then
restores only services that were previously running. A failure restarts the
previous running set and leaves no complete marker.

`scripts/verify_restore.sh` rejects a wrong key, changed/truncated ciphertext,
missing/extra members, a changed manifest, database/object inventory mismatch,
wrong migration revision, or missing PostGIS. It restores the database under a
disposable isolated name and objects under a disposable verification prefix,
compares stored-file rows with exact restored object bytes, then deletes the
isolated targets. No traffic points at them. Retention is at most 35 days; the
approved operator implements off-host lifecycle and deletion in the chosen
account.

## Observability and alerts

Caddy, API, and worker emit structured JSON with edge request IDs and release
revision. Application/Sentry scrubbers redact authorization/cookies/tokens,
passwords/secrets/API keys, NIN/BVN, bank values, precise GPS/coordinates, raw
fraud evidence when keyed, and private URLs; exception bodies and local
variables are not exported. Never log environment files, smoke responses,
backup plaintext, object manifests containing live keys, or presigned URLs.

The approved platform must alert the named `EXT-OPERATIONS-OWNER` on:

| Signal | Threshold/action |
|---|---|
| Edge/API availability | sustained non-2xx or readiness failure; keep/reclose traffic |
| Migration | any non-zero or image-head mismatch; traffic remains stopped |
| Worker | missing/stale heartbeat or growing queue; pause traffic-affecting release and inspect jobs |
| Dead work | failed job/retry exhaustion; preserve job/request ID and sanitized exception class |
| Storage | canary write/read/delete or report publication failure; block issuance/download |
| Backup | missing complete marker, digest/manifest/restore failure, or retention breach |
| Report issuance | queued/running lease age, failed pair publication, or storage mismatch |

Provider-specific metrics/alert syntax is intentionally deferred to
`EXT-RELEASE-ENV`; the invariants and event fields are not.

## Incident playbooks

Every incident record names the `EXT-OPERATIONS-OWNER`, affected release ID,
first/last event time, sanitized correlation IDs, impact, containment,
recovery evidence, and rotation/follow-up owner. Never copy live payloads.

- **Credential rotation:** keep traffic or the affected integration stopped;
  create the new secret in the approved store; update the protected env;
  preflight; rotate database/Redis/object credentials in a coordinated window;
  recreate affected services; run readiness/smoke; revoke the old credential;
  record only secret identifiers and times. JWT rotation intentionally
  invalidates sessions. Backup keys require retaining the old key until every
  bundle under its retention window has expired or been re-encrypted and
  restored successfully.
- **Worker backlog/dead letters:** block release/issuance if heartbeat is
  stale; record queue depth and oldest sanitized job ID; remove the cause;
  restart the worker; replay only through the job's existing idempotent
  identity; prove depth falls and report/storage state converges. Never delete
  Redis data or manufacture success.
- **Migration failure:** edge stays stopped. Compare image head and database
  current. If equal, treat it only as response loss and continue through the
  scripted reconciliation. Otherwise preserve logs and backup, stop. Do not
  downgrade or hand-edit production schema.
- **Storage outage:** block upload, report publication and download; preserve
  database authority; restore credentials/connectivity; run the write/read/
  delete canary; reconcile pending report jobs through their existing request
  identities. Do not expose the bucket or substitute local files.
- **Report issuance recovery:** keep live issuance flags and legal/method gates
  unchanged; inspect job/request/lease and immutable pair state using sanitized
  identifiers; restore worker/storage; invoke the existing retry/reissue path;
  require both CSV/PDF objects and stored-file evidence to agree before access.
- **Rollback/recovery:** use the previous exact image environment and
  `recover_release.sh`; never imply schema rollback. If compatibility proof is
  absent, keep traffic stopped.
- **Disaster restore:** obtain incident-owner approval, verify the encrypted
  bundle in isolation, compare database/object manifest and revision, then
  produce a separate traffic-switch plan. This preparation does not automate
  destructive replacement of populated production data.

## Local rehearsal

`scripts/rehearse_w403a.sh` creates a dedicated Compose project, private
versioned MinIO, synthetic report object/row, exact labelled images, fresh
PostGIS/Redis, and disposable secrets. It runs all migrations, layered
readiness, a 100-request bounded load, encrypted backup, isolated database and
object restore, and same-revision recovery. Its trap removes the dedicated
containers, network, volumes, files, passphrases, and backup bundle on success
or failure. It is strong repository preparation evidence, not
`DV-STAGING-LIVE`.
