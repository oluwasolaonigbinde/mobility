# Mobility operations runbook

This runbook covers the Docker Compose pilot stack. Run commands from the repository root. Production-like environments must use externally supplied credentials and explicit hostnames, require TLS and authentication for both PostgreSQL and Redis, keep both private, and put the frontend behind a trusted TLS edge. Bundled and managed data services are both permitted; do not infer provider values from this repository.

## Stack overview

| Component | Compose service | Internal address | Purpose |
|---|---|---|---|
| Next.js BFF | `frontend` (`full` profile) | `frontend:3000` | Browser entry point and httpOnly session-cookie owner |
| FastAPI | `api` | `api:8000` | API, auth, analytics, fraud, and payouts |
| arq worker | `worker` | none (no port) | Automated post-trip processing pipeline and sweep |
| PostGIS | `db` | `db:5432` | System of record |
| Redis | `redis` | `redis:6379` | Login-rate-limit counters and the arq job queue |

Local port mappings are development conveniences. Do not expose API `8000`, frontend `3100`, Postgres, or Redis on a public host. Staging should expose only ports 80/443 on the reverse proxy.

Basic checks:

```bash
docker compose ps
docker compose logs --tail=100 api frontend db redis
docker compose exec -T api python -c 'from urllib.request import urlopen; print(urlopen("http://127.0.0.1:8000/api/v1/health", timeout=3).read().decode())'
```

Never stop or kill a process on host port 3000 while operating this repository; it may belong to another project.

## Provider-neutral pre-production topology

The current provider-neutral production contract, exact release/recovery
commands, encrypted database-plus-object backup, isolated restore, incident
playbooks and the future external run sheet are maintained in
`docs/w4-03a-release-operations.md`. `docker-compose.production.yml` is now a
standalone, image-only release model; it must **not** be merged with the local
development Compose file. The database-only sections below remain local
development recovery tools; they are not the W4-03A production backup or
release path.

### Production data-service TLS and edge preflight

`production.env.example` names six external file authorities for the bundled
adapter: a CA, server certificate and private key for each of PostgreSQL and
Redis. Keep all six outside the repository. Private keys must be readable only
by their owner (mode 0600 or stricter). Before Compose starts, run the same
preflight used by the release script:

```bash
python3 scripts/release_contract.py preflight \
  --env-file /absolute/path/to/approved-production.env \
  --expected-checkout-revision "$(git rev-parse HEAD)"
```

Preflight fails without printing certificate contents when a file is missing,
inside the repository, too permissive, signed by the wrong CA, missing the
`db` or `redis` SAN, or paired with the wrong private key. The bundled services
copy this material into service-owned tmpfs; PostgreSQL rejects `hostnossl` and
requires SCRAM over verified TLS, while Redis disables its plaintext port and
requires password authentication over verified TLS. Healthchecks and
`scripts/release_smoke.sh` use those same CAs and service names.

The staging and production examples carry the same complete key set. Preflight
derives the application portion from the current `Settings` class and the
deployment portion from production Compose, so a newly added setting cannot be
silently omitted from a release environment. Every copied environment file must
name the complete contract even when an external gate remains deliberately
blank or false. Placeholder values are always rejected.

Before staging or production can start, the live path additionally requires a
configured scanner, retained trip-evidence signing keyring, approved privacy
collection reference, authenticated STARTTLS SMTP adapter with an independent
receipt key, an approved HTTPS basemap build input, and complete evidence and
activity-policy inputs. The checked-in examples intentionally contain blanks,
false gates, and `EXAMPLE-ONLY` markers, so neither file is deployable. Replace
them only with externally approved values in the mode-0600 copy outside the
repository; never weaken preflight to make an example pass.

The basemap build URL must be a deployable HTTPS URL without query credentials.
It is included in the release configuration digest, and the post-pull
`--check-images` preflight confirms that the immutable frontend artifact contains
the exact approved build input. A runtime environment value cannot replace a
different value compiled into the image.

Managed PostgreSQL and Redis are valid production configuration when their URLs
contain explicit authenticated host authorities and peer-verified TLS. The
current release, backup, restore and recovery commands are nevertheless the
bundled adapter and stop managed URLs with
`MANAGED_DATA_RELEASE_ADAPTER_REQUIRED`. Do not point those commands at managed
services or weaken verification; the later managed adapter must supply its own
backup/restore and platform evidence. No provider, hostname, certificate or
credential is supplied by this repository.

The public edge must use the repository Caddy policy unchanged unless a
security review approves a replacement. It overwrites inbound client identity
with the accepted socket peer and a generated request ID, rejects framing, and
keeps only the PWA-required geolocation, wake-lock and clipboard capabilities.

## Database backups

Create a custom-format `pg_dump`:

```bash
scripts/db_backup.sh
```

The script writes `backups/mobility_<UTC timestamp>.dump` with mode `0600` and retains the newest 14 dumps. `backups/` is gitignored. This is local pilot retention, not disaster recovery: copy selected dumps to encrypted off-host storage and test those copies regularly.

Check that a dump is readable without restoring it:

```bash
docker compose exec -T db pg_restore --list < backups/mobility_YYYYMMDDTHHMMSSZ.dump >/dev/null
```

## Restore

The restore script validates the dump before stopping writers. It restores into `mobility_restore_tmp`, validates the dump's Alembic revision, then renames databases. It never streams a restore into the live database.

```bash
scripts/db_restore.sh backups/mobility_YYYYMMDDTHHMMSSZ.dump
```

Type `RESTORE` when prompted. If the dump is at a known revision older than the checked-out head, review the intervening migrations and opt in:

```bash
scripts/db_restore.sh --upgrade backups/mobility_YYYYMMDDTHHMMSSZ.dump
```

The sequence is:

1. `pg_restore --list` pre-validates the file while the application remains up.
2. The script captures the checked-out Alembic head and previous frontend/worker state, then stops API/frontend/worker writers.
3. It restores and validates `mobility_restore_tmp`.
4. It renames live `mobility` to `mobility_pre_restore_<UTC timestamp>` and the temporary database to `mobility`.
5. With `--upgrade`, it migrates the restored database to the checked-out head.
6. It starts the API, restores the frontend and worker only when each was
   previously running, and polls the API health endpoint for up to 40 seconds.

On a failure before the first rename, the script removes the temporary database and restarts the application; the live database is untouched. If only the first rename completed, it renames the safety database back automatically. If a post-swap migration, restart, or health check fails, it retains the failed restored database as `mobility_failed_restore_<timestamp>` and swaps the original back. The error output names the stage and prints exact recovery or pruning commands. If automatic recovery itself fails, keep application writers stopped and follow the SQL printed by the script from a `psql` session connected to `postgres`.

After application and data verification, prune the retained safety database using the exact command printed by the script, for example:

```bash
docker compose exec -T db dropdb -U mobility mobility_pre_restore_yyyymmddthhmmssz
```

Restore rehearsal before release (copy the whole block from the repository
root). It uses its own Compose project and named volume, creates a deterministic
marker, proves a valid restore returns the original value, proves the retained
safety database contains the intentional mutation, compares the database
revision exactly with the single checked-out Alembic head, and proves a
truncated dump cannot change the live database. The trap removes the disposable
stack, volume, dump, and temporary files on success or failure:

```bash
(
set -Eeuo pipefail
export COMPOSE_PROJECT_NAME=mobility-restore-drill
export COMPOSE_FILE="$PWD/docker-compose.yml:$PWD/docker-compose.production.yml"
export COMPOSE_ENV_FILES="$PWD/staging.env.example"
BACKUP_PATH=""
BACKUP_DIR="$(mktemp -d /tmp/mobility-restore-drill-backups.XXXXXX)"
export BACKUP_DIR
INVALID_DUMP="$(mktemp /tmp/mobility-invalid-dump.XXXXXX)"
cleanup_restore_drill() {
  docker compose --profile full --profile worker --profile release down -v --remove-orphans || true
  rm -rf -- "$BACKUP_DIR"
  rm -f -- "$INVALID_DUMP"
}
trap cleanup_restore_drill EXIT

# Remove a volume left by an interrupted earlier rehearsal before creating data.
docker compose --profile full --profile worker --profile release down -v --remove-orphans
docker compose build api
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose exec -T db psql -U mobility -d mobility -v ON_ERROR_STOP=1 \
  -c "CREATE TABLE restore_drill_marker (id integer PRIMARY KEY, marker text NOT NULL); INSERT INTO restore_drill_marker VALUES (1, 'known-before-backup');"

BACKUP_OUTPUT="$(scripts/db_backup.sh)"
printf '%s\n' "$BACKUP_OUTPUT"
BACKUP_PATH="$(printf '%s\n' "$BACKUP_OUTPUT" | sed -n 's/^Backup complete: //p')"
test -n "$BACKUP_PATH"
docker compose exec -T db psql -U mobility -d mobility -v ON_ERROR_STOP=1 \
  -c "UPDATE restore_drill_marker SET marker = 'known-after-backup-mutation' WHERE id = 1;"
printf 'RESTORE\n' | scripts/db_restore.sh "$BACKUP_PATH"

RESTORED_VALUE="$(docker compose exec -T db psql -U mobility -d mobility -At \
  -c 'SELECT marker FROM restore_drill_marker WHERE id = 1;')"
test "$RESTORED_VALUE" = "known-before-backup"
SAFETY_DB="$(docker compose exec -T db psql -U mobility -d postgres -At \
  -c "SELECT datname FROM pg_database WHERE datname LIKE 'mobility_pre_restore_%' ORDER BY datname DESC LIMIT 1;")"
test -n "$SAFETY_DB"
SAFETY_VALUE="$(docker compose exec -T db psql -U mobility -d "$SAFETY_DB" -At \
  -c 'SELECT marker FROM restore_drill_marker WHERE id = 1;')"
test "$SAFETY_VALUE" = "known-after-backup-mutation"

CODE_HEADS="$(docker compose run --rm -T --no-deps api alembic heads | awk 'NF {print $1}')"
DB_CURRENTS="$(docker compose exec -T db psql -U mobility -d mobility -At \
  -c 'SELECT version_num FROM alembic_version;')"
test "$(printf '%s\n' "$CODE_HEADS" | awk 'NF {count++} END {print count+0}')" -eq 1
test "$(printf '%s\n' "$DB_CURRENTS" | awk 'NF {count++} END {print count+0}')" -eq 1
CODE_HEAD="$(printf '%s\n' "$CODE_HEADS" | awk 'NF {print; exit}')"
DB_CURRENT="$(printf '%s\n' "$DB_CURRENTS" | awk 'NF {print; exit}')"
test "$DB_CURRENT" = "$CODE_HEAD"

docker compose exec -T db psql -U mobility -d mobility -v ON_ERROR_STOP=1 \
  -c "UPDATE restore_drill_marker SET marker = 'unchanged-after-invalid-restore' WHERE id = 1;"
head -c 64 "$BACKUP_PATH" > "$INVALID_DUMP"
if printf 'RESTORE\n' | scripts/db_restore.sh "$INVALID_DUMP"; then
  echo 'ERROR: truncated dump unexpectedly restored' >&2
  exit 1
fi
docker compose ps --status running --services | grep -qx api
AFTER_INVALID="$(docker compose exec -T db psql -U mobility -d mobility -At \
  -c 'SELECT marker FROM restore_drill_marker WHERE id = 1;')"
test "$AFTER_INVALID" = "unchanged-after-invalid-restore"

cleanup_restore_drill
trap - EXIT
)
```

## Migrations

Before migrating, take a backup and inspect the pending revisions:

```bash
docker compose exec -T api alembic current
docker compose exec -T api alembic history --indicate-current
scripts/db_backup.sh
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
```

Apply migrations before starting newly deployed application code. A migration rollback is allowed only when its revision file documents a safe downgrade and no incompatible data has been written. Prefer restoring the pre-migration backup over improvising destructive SQL.

## Sessions, password changes, and logout

- Access tokens slide in 60-minute windows during eligible GET navigation, up to an absolute 12-hour lifetime from the original login.
- Logout calls the private BFF session-revocation route, increments the user's
  durable `session_version`, and then clears the current cookie. Every bearer
  issued before that commit is rejected on every device. A 401/403 response
  clears an already-invalid local cookie without claiming a new global
  revocation. If backend revocation cannot be confirmed, the local session is
  retained so the user can retry, the UI displays the failure, and no logout is
  broadcast to other tabs.
- A password change increments the user's `session_version`; every other token for that user is rejected immediately. The fresh token returned by the change-password flow remains valid.
- Admin-created users have `must_change_password=true` and are sent to the role-appropriate password-change screen on first login.
- Rotating `JWT_SECRET_KEY` invalidates every current session immediately.

### Forgotten-password break glass

There is intentionally no public reset-by-email flow. For an identity-verified user, generate an Argon2 hash inside the API container:

```bash
docker compose exec api python -c 'from getpass import getpass; from app.core.security import hash_password; print(hash_password(getpass("Temporary password: ")))'
```

Open `psql`, use `\set` so the email and generated hash are quoted as values, and run the update in a transaction:

```bash
docker compose exec db psql -U mobility -d mobility
```

```sql
\set email 'person@example.com'
\set password_hash '$argon2id$...paste the complete generated hash...'
BEGIN;
UPDATE users
SET password_hash = :'password_hash',
    must_change_password = true,
    session_version = session_version + 1,
    updated_at = now()
WHERE email = lower(:'email')
RETURNING id, email, must_change_password, session_version;
COMMIT;
```

Require exactly one returned row. The session bump immediately revokes possibly compromised sessions; the user must replace the temporary password at next login. Record the operator, reason, and timestamp in the incident record. A future admin-reset endpoint may replace this procedure, but is not part of F7.

## Driver PWA session behavior

While tracking, the mounted PWA sends a lightweight GET keepalive every 10 minutes. Middleware can refresh a near-expiry session without downloading a full page. Keepalive errors are fail-open and retried: buffered pings remain client-side, and a later flush surfaces the existing error if the session ultimately expires. No refresh can cross the 12-hour absolute login cap, so a trip longer than 12 hours must reauthenticate.

Logout and refresh serialize on the same locked user row. If refresh commits
first, logout immediately invalidates the refreshed bearer; if logout commits
first, refresh returns `SESSION_REVOKED` and writes no refresh event. The logout
broadcast occurs only after the backend confirms revocation, then stops active
tracking in other open tabs before they navigate to the login page.

The manifest and service worker are scoped to `/driver`. The forced first-login route `/driver/change-password` stays inside that scope. The shared `/login` route does not: if a driver's session fully expires, a standalone PWA can show browser scope-escape UI until navigation returns below `/driver`. This predates F7 and needs a separate product decision about a driver-scoped login or a wider manifest scope.

## Login rate limiting

Default failure/in-flight thresholds are:

| Bucket | Limit | Window |
|---|---:|---:|
| Normalized account | 5 | 15 minutes |
| Client IP | 150 | 5 minutes |
| Platform global | 250 | 5 minutes |

Successful login deletes the account counter and refunds its IP/global reservation. Redis/Lua reserve errors return `503 RATE_LIMIT_UNAVAILABLE` with `Retry-After` before password verification; a refund failure after valid credentials is warning-only and may overcount until TTL expiry. The login form presents backend `429` responses and the retry delay.

Password-change attempts share the same buckets so a stolen session cannot brute-force the current password: a wrong current password keeps its reservation and is audited as `auth.password.change_failed`; proving the current password refunds it. Limit transitions appear as `auth.password.change_rate_limited`.

With client-header trust disabled, FastAPI uses its direct socket peer. Browser login calls arrive through the BFF, so they share the Next server's IP bucket. An unauthenticated attacker sustaining roughly 150 junk form submissions per five-minute window can therefore block all web-UI logins; 250 failures fill the global bucket. The per-account bucket remains the primary credential-guessing control in this topology. Repeating `auth.login.rate_limited` records with `bucket=ip` or `bucket=global` in `/admin/audit` identify this condition.

Clear only login limiter keys during an approved lockout response:

```bash
docker compose exec -T redis sh -c "redis-cli --scan --pattern 'ratelimit:login:*' | xargs -r redis-cli DEL"
```

This is temporary relief, not a substitute for blocking the source at the edge. Do not flush unrelated Redis data.

### Production trusted-edge authority

The production Compose topology enables login client-IP relay only through the
exact private frontend address `10.255.254.10/32` on the dedicated
`10.255.254.0/24` application network. Release preflight rejects disabling the
relay/trust pair, broadening that CIDR, or moving the frontend address. Do not
copy this authority to a different topology without a new edge review. Its
required invariants are:

1. A public reverse proxy is the only client entry point and derives client identity from its accepted TCP socket peer, not from a client-supplied forwarding header.
2. The proxy discards the inbound `X-Client-IP` value by overwriting it from the accepted socket peer, and does not preserve a client-supplied `X-Forwarded-For` value.
3. Next passes only that proxy-created value through the login action; it never parses `X-Forwarded-For` itself.
4. Both API `8000:8000` and frontend `3100:3000` host mappings are unpublished. Postgres and Redis mappings are also unpublished.
5. `LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS` contains only the BFF container network(s) FastAPI sees as its direct peer. An empty allowlist means trust nobody.
6. A test proves forged direct headers cannot select a limiter bucket and distinct edge socket peers do receive distinct buckets.

If any condition is absent in a replacement topology, stop release rather than
falling back to a shared browser-login bucket. The browser-to-API path is
`browser → edge → Next/BFF → FastAPI`; FastAPI trusts the relayed value only
when the direct BFF peer is that exact `/32`. Driver-registration header trust
remains off until its separate BFF relay is reviewed.

## Post-trip processing worker

The `worker` service runs an arq worker (`arq app.jobs.worker_entry.WorkerSettings`) that completes the pipeline for **sealed** trips (D15 — a trip seals at end when the client watermark is satisfied, when a late batch completes it, or via the seal sweep after `TRIP_SEAL_GRACE_SECONDS`; the money chain never runs on merely-ended trips): analytics and fraud flags, one current-formula impression estimate, and one current-formula payout calculation plus its ledger entry. It fills missing stages and refreshes an existing impression estimate when its analytics or open-fraud inputs are stale; it never rewrites a historical payout, and old-formula analytics must be recomputed through the admin endpoint. Work arrives two ways: a fail-open enqueue after each seal commit, and a periodic sweep that derives due (sealed) trips from Postgres. A sibling seal sweep on the same cadence force-seals ended trips past the recovery grace and logs `job=seal_ended_trips sealed=... enqueued=...`. The strict entry module rejects a missing `REDIS_URL` before arq constructs a worker or opens a socket.

```bash
docker compose up -d worker
docker compose logs -f worker
docker compose stop worker
```

The worker publishes no host port. Settings: `WORKER_SWEEP_INTERVAL_MINUTES` (default `5`; must be a divisor of 60 between 1 and 60 — anything else fails Settings validation at startup), `WORKER_SWEEP_BATCH_SIZE` (default `25` trips per sweep), and `TRIP_SEAL_GRACE_SECONDS` (default `600` — how long an incomplete/legacy trip end waits for late GPS batches before the seal sweep finalizes it).

| Failure | Effect | Recovery |
|---|---|---|
| Redis down at trip end | Trip end still returns 200; API logs a `event=trip_enqueue_failed` warning | Sweep completes the trip within one interval |
| Redis data loss (flush, restart) | Queued jobs lost | Sweep re-derives all due work from Postgres |
| Worker down | Ended trips accumulate unprocessed | Start the worker; sweeps drain the backlog in batches |

Watch for `job=process_trip trip_id=... overall=... stages=...` per enqueued trip and `job=process_unprocessed_trips selected=... processed=... partial=... failed=... skipped=...` per sweep. A non-zero `failed` count, with a stackful log and a Sentry event per failure when a DSN is set, means trips need operator attention. Savepoint convergence handles the six known uniqueness races inside the write services; any integrity error that escapes those services is a real failure and remains visible.

The sweep reads due-work facts only from Postgres and attempts at most one keyset page per occurrence (`WORKER_SWEEP_BATCH_SIZE`, 25 trips by default). Its last `(ended_at, trip_id)` cursor is a disposable Redis traversal hint: the next occurrence resumes at the following page, and a short or empty page clears the cursor so the subsequent occurrence wraps to the oldest due trip. Redis loss merely restarts that traversal; it cannot mark work complete. Therefore a corrupt prefix can consume one occurrence but cannot permanently starve healthy trips behind it.

Positive current-formula payout calculations missing ledger entries are money-invariant repair work. The sweep selects them even when analytics is on an old formula, heals every missing ledger for the trip, and audits all created ledger IDs. Zero, blocked, and insufficient-data calculations remain terminal. Old-formula analytics otherwise blocks impressions and payouts until the admin recompute endpoint writes the configured formula. Downstream rows carry source fingerprints; changed analytics requires an estimate refresh, and a payout whose source fingerprint changed fails clearly with `PAYOUT_CALCULATION_STALE` instead of rewriting historical money.

Each trip run reads one timestamp from the database clock and injects it through analytics, impression, and payout services. This keeps the worker path frozen-time testable and prevents stages in one run from acquiring unrelated application-clock timestamps.

**Money model.** The automated payout stage dispatches per the governing rule row's model: `payout_v2` (the approved hourly-pay engine, S1/D9 — Q4/Q5 adopted and delivered) or frozen `payout_v1` history. Since S4 the worker also owns the location-ping data lifecycle (partition premake, coverage alarm, retention purge), so running it in every deployed environment is mandatory, not optional.

## Location-ping data lifecycle (S4)

`location_pings` is range-partitioned by UTC month on `recorded_at`
(migration `0014`; the pre-conversion table survives as the bounded
partition `location_pings_legacy`). Three daily worker crons own the
lifecycle — **running the worker is mandatory in production from S4
onward** (`docker compose --profile worker up -d worker` in the production
topology): retention enforcement is a legal obligation, and partition
premake prevents a write outage on the hottest table.

| Cron | What it does | Settings |
|---|---|---|
| `premake_ping_partitions` | Idempotently creates monthly partitions covering the current UTC month through now + `PARTITION_PREMAKE_MONTHS` (default 4). Coverage-based, so it coexists with the legacy partition. Runs the coverage check inline afterward. | `PARTITION_PREMAKE_MONTHS` |
| `check_ping_partition_coverage` | Alarms when no partition covers now + 1 month: logs `status=uncovered`, captures to Sentry, and fails the job. | — |
| `purge_expired_ping_partitions` | Drops partitions whose entire range is older than `PING_RETENTION_MONTHS` (default 12), with append-only evidence in `data_purge_audit`, then deletes ping batches that have zero remaining pings and are older than the window. Concurrent runs no-op via an advisory lock. | `PING_RETENTION_MONTHS` |

**Monitoring (both detectors must be wired):**

- Point uptime monitoring at `GET /api/v1/health/partitions` — 200 with
  `covered_until` when a partition covers now + 1 month, 503 `degraded`
  otherwise (also 503 if the table is not partitioned). This catches a dead
  worker; do not fold it into `/ready` (a month-out coverage gap must not
  drop live traffic).
- Alert on Sentry events from `check_ping_partition_coverage` /
  `premake_ping_partitions` failures.

**Purge evidence.** Every purge writes `data_purge_audit` lifecycle rows:
`purge_started` (with row count, range, retention config) commits **before**
any destruction; `dropped` commits atomically with the `DROP TABLE`; a
partial unique index allows exactly one `dropped` row per partition;
`detach_finalized` records recovery of an interrupted concurrent detach.
The table is append-only — never UPDATE or DELETE it. An interrupted run
honestly shows `purge_started` without `dropped` and the next daily run
completes it. Recovery is deliberately gated: a pending detach is FINALIZEd
only when a matching `purge_started` row exists **and** the partition is
still retention-expired under current settings — anything else (a manual
detach, a widened retention window) is refused with an error log
(`pending_detach=... outcome=refused`) plus a Sentry event, and the run
skips all destruction (partition sweep and batch purge) until an operator
resolves it, because a pending partition is invisible through the parent
and purging around it could cascade-delete retained pings. Standalone
partition tables are dropped only when the evidence trail claims them and
no `dropped` evidence already exists for the name (a conflict fails the run
closed with `outcome=drop_refused`); an `orphan=... outcome=unclaimed_table`
error log means a table the job refuses to touch: investigate manually.

**Backups respect retention (§24.2.5):** backup rotation must stay ≤ 35
days so purged pings age out of backups automatically. The local
`scripts/db_backup.sh` enforces both newest-14 and age-at-most-35-days bounds;
`BACKUP_RETENTION_DAYS` may narrow that age but cannot exceed 35. Keep approved
encrypted off-host copies on the same or a shorter bounded rotation. The
cross-store request procedure is in `docs/data-subject-request-runbook.md`.

| Failure | Effect | Recovery |
|---|---|---|
| Worker down for days | Coverage shrinks; `/health/partitions` 503s ~1 month before writes would fail | Start the worker; premake catches up idempotently (4-month horizon ≈ 3 months of headroom) |
| `no partition of relation found for row` on ping insert | Coverage exhausted (both alarms ignored) | Start worker or run premake once; the insert path recovers immediately — no data was lost, the write was rejected |
| Retention crash mid-run | `data_purge_audit` shows the interrupted state | Next daily run recovers (evidence-gated FINALIZE + evidenced-orphan drop); no manual SQL needed |
| Purge job logs `pending_detach=... outcome=refused` | A pending detach lacks purge evidence or is no longer retention-expired | Destruction is paused (sweep + batch purge skipped). Investigate: if the detach is legitimate, `ALTER TABLE location_pings DETACH PARTITION <name> FINALIZE` manually and dispose of the table deliberately; never let a pending detach linger |
| Purge job logs `outcome=drop_refused` (run fails) | `dropped` evidence already exists for a table that is present again | Manual investigation — the evidence cannot account for the table; the job fails closed and retries daily |
| Purge job logs `outcome=unclaimed_table` | A standalone `location_pings_*` table exists without evidence | Investigate manually before any drop — the job will never touch it |

## Local Playwright reset and overrides

Playwright runs projects fully in parallel. Use a clean persistent database and relaxed local test thresholds:

```bash
docker compose down -v
export LOGIN_RATE_LIMIT_ACCOUNT_MAX_FAILURES=50
export LOGIN_RATE_LIMIT_IP_MAX_FAILURES=500
docker compose up -d
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m app.seeds.demo
cd frontend && npm run test:e2e
```

The volume reset is destructive and is for local demo/e2e data only. CI uses a fresh database and applies the same rate-limit overrides. If a previous local run filled a bucket, use the targeted Redis command in the rate-limit section.

## Demo seed

`python -m app.seeds.demo` introspects the live Alembic head and is deterministic and append-only for a given seed namespace. Rerunning it must not duplicate trips or rewrite existing ledger amounts. `F7_SEED_MAX_TRIPS_PER_DAY` controls density: local default `2`; CI uses `1` so its deterministic key set is a strict subset. Staging is in the seed's production-environment denylist, so setting `ALLOW_DEMO_SEED` alone does not permit a staging seed. Do not weaken that guard without written approval and a disposable database.

Measurements from the 12 Jul 2026 local Docker/PostGIS verification host:

| Path | Density | Budget | Last measured |
|---|---:|---:|---|
| Compose-style clean seed | 1 | 4 minutes | 5.66 seconds (178 F7 trips) |
| Backend PostGIS seed tests | 1 | 10 minutes | 26.80 seconds (12 tests) |
| Local comparison | 2 | Informational | 8.27 seconds (318 F7 trips) |

Re-measure on the hosted CI runner after the first workflow run. If density 1 exceeds budget there, reduce the CI rolling window or share a module seed as specified by the tests; do not change the local default or legacy objects merely to hide runtime.

## Sentry-ready error tracking

All hooks are inert when their DSN is empty. No Sentry account is created by this repository.

- FastAPI uses runtime `SENTRY_DSN`, with tracing disabled and default PII collection off. Restart the API after changing it.
- Next server instrumentation uses runtime `SENTRY_DSN`. Restart the frontend after changing it.
- Browser instrumentation uses `NEXT_PUBLIC_SENTRY_DSN`, which Next.js inlines at build time. For the containerized frontend, set the value and rebuild: `NEXT_PUBLIC_SENTRY_DSN=... docker compose build frontend`. A restart without a rebuild does not enable or change browser reporting.
- Local `npm run dev` reads `frontend/.env.local` at dev startup.
- Removing a browser DSN also requires rebuilding the image. No source-map upload token is configured.

Confirm an inert build before enabling a real DSN, use a non-production/dummy DSN for a controlled exception, and check that neither request bodies nor credentials appear in captured events.

## Private file and KYC incidents

Production storage, malware scanner and key-custody selections remain external
deployment inputs. The local MinIO, ClamAV and keyring adapters prove the
provider-neutral contracts; they are not production-provider approval.

KYC retention execution is disabled unless an approved positive
`FILE_KYC_RETENTION_DAYS` value is configured. Do not copy a local or synthetic
test value into a live environment. After legal/privacy approval, an active
admin must run the dry-run first and reconcile its eligible count before any
execution:

```text
POST /api/v1/admin/operations/file-kyc-retention
{"dry_run":true,"reason":"approved_retention_review_reference"}
```

Only rejected or expired submissions older than the configured cutoff are
eligible. Pending and approved submissions remain untouched. The worker uses
the same boundary once daily; without the setting it records
`policy_configured=false` and deletes nothing. Execution removes document links
before deleting an object, preserves any file still referenced by another KYC,
vehicle-evidence or campaign record, and writes redacted submission/file/run
audit events. A storage deletion error rolls the database transaction back and
is safe to retry; the object store remains private throughout.

| Failure | Fail-closed effect | Recovery evidence and action |
|---|---|---|
| Scanner unavailable or timing out | File stays quarantined; confirmation, download, creative/KYC use and approval cannot treat it as clean | Restore the configured scanner, verify the worker records a successful clean scan for the same stored-file ID, then retry the blocked workflow. Never edit scan status manually. |
| Private storage unavailable | Upload confirmation, reads and retention object deletion return unavailable; no public URL or database-only purge is allowed | Restore the configured storage endpoint/credentials, verify a private signed read and an unsigned denial, then rerun the bounded operation. A retention retry may encounter an already-absent object after a partial external deletion; deletion remains idempotent. |
| Active key unavailable or ciphertext authentication fails | NIN/bank reveal, new encryption and rewrap fail; masked records remain readable but plaintext is never substituted or logged | Restore the exact approved key version through the custody adapter and rerun a masked/reveal check under an audited purpose. If the key is irrecoverable, preserve the ciphertext and escalate to the privacy/security owner; do not overwrite it with guessed data or a new identity. |
| Retention policy absent or invalid | Scheduled deletion is disabled and an execution request returns `FILE_KYC_RETENTION_POLICY_REQUIRED` | Obtain the missing legal/privacy decision, record its production configuration reference, configure the approved positive day count, run dry-run, then execute only after reconciliation. |
| Concurrent retention run | One PostgreSQL advisory-lock holder proceeds; another reports `lock_acquired=false` and deletes nothing | Let the holder finish, inspect `file_kyc.retention_executed` audit counts, then rerun normally if eligible records remain. |

Incident records must identify the environment, stored-file/submission IDs,
time window, observed error code, operator and recovery evidence. Do not include
filenames, NIN, bank values, object credentials, ciphertext keys or scanned
file contents. Whole-platform breach, ROPA and DSR handling remains owned by
W3-00A/B.

## Secret rotation

Keep secrets in the host/platform secret store, not Git or image layers. Rotate one dependency at a time and retain a tested rollback value until health checks pass.

1. Take a database backup and record the current deployment revision.
2. Rotate the database password in Postgres, update `POSTGRES_PASSWORD` and `DATABASE_URL`, recreate API/database services as required, then check readiness.
3. Rotate Redis authentication and its TLS certificate/key/CA material together in the private topology, update the verified `REDIS_URL`, then test limiter degradation and recovery. Rotate PostgreSQL TLS material with its matching URL/CA authority in the same deliberate one-dependency-at-a-time manner.
4. Rotate `JWT_SECRET_KEY` during a communicated window. This intentionally logs out every user immediately.
5. Rotate Sentry DSNs at runtime for servers; rebuild the frontend for `NEXT_PUBLIC_SENTRY_DSN`.
6. Revoke the old value only after API health, login, tracking, and admin checks pass.

## Common failures

| Symptom | Check | Response |
|---|---|---|
| API not ready | `docker compose logs api db`; `/api/v1/health/ready` | Confirm PostGIS is running and migrations are at head; do not repeatedly restart the database during recovery. |
| `password authentication failed` | Database and API secret versions | Restore a matching `POSTGRES_PASSWORD`/`DATABASE_URL`, then rotate deliberately. |
| `relation ... does not exist` | `alembic current` versus `alembic heads` | Stop new writers, back up, and run reviewed pending migrations. |
| All web logins return 429 | `/admin/audit` rate-limit transitions and Redis TTLs | Block the attacking source at the edge; clear only `ratelimit:login:*` keys if approved. |
| One account returns 429 | Normalized account bucket and retry time | Wait for expiry or clear the targeted limiter keys after verifying identity; do not disable the limiter globally. |
| Redis unavailable during login/password change | `503 RATE_LIMIT_UNAVAILABLE`, API warning logs, `/api/v1/health/ready` | Restore authenticated TLS Redis, confirm its script and worker-heartbeat components are `ok`, then retry. Do not bypass the limiter. |
| Driver pings stop flushing | Device network, tracker error, 12-hour cap | Keep the app visible, preserve buffered pings, reauthenticate if the absolute cap passed, and retry. |
| Restore stops after a rename | Script's stage/recovery output and database names | Keep writers stopped; follow the exact printed recovery SQL. Never drop the safety database first. |
| Browser Sentry remains silent | Image build arguments | Rebuild with `NEXT_PUBLIC_SENTRY_DSN`; a container restart is insufficient. |
| Local e2e assertions drift | Persistent demo/e2e records | Reset only the intended local Compose volumes, reseed, and rerun with test rate limits. |
