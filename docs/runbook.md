# Mobility operations runbook

This runbook covers the Docker Compose pilot stack. Run commands from the repository root. Production-like environments must replace local credentials, keep Postgres and Redis private, and put the frontend behind a trusted TLS edge.

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

`docker-compose.production.yml` is an overlay for `docker-compose.yml`; always
pass both files, in that order. Its explicit reset tags remove development host
ports, source mounts, reload commands, and the frontend's opt-in profile. Docker
Compose v2.33.1 or newer is required for reset tags, explicit egress gateway
priority, and the long-form health
dependencies used here. Copy `staging.env.example` to a
root-readable path outside the repository, replace every `EXAMPLE-ONLY` value,
and keep it out of source control.

The release sequence is explicit:

```bash
export COMPOSE_FILE="$PWD/docker-compose.yml:$PWD/docker-compose.production.yml"
export COMPOSE_ENV_FILE=/secure/path/mobility-staging.env
export COMPOSE_ENV_FILES="$COMPOSE_ENV_FILE"

# Render, validate, and build. A missing mandatory value fails the render.
docker compose --env-file "$COMPOSE_ENV_FILE" config >/dev/null
docker run --rm -e EDGE_HOSTNAME=http://localhost \
  -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.8-alpine caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file "$COMPOSE_ENV_FILE" build api frontend

# Start dependencies, apply migrations as a one-shot, then start the app.
docker compose --env-file "$COMPOSE_ENV_FILE" up -d db redis
docker compose --env-file "$COMPOSE_ENV_FILE" --profile release run --rm migrate
docker compose --env-file "$COMPOSE_ENV_FILE" up -d api frontend edge
docker compose --env-file "$COMPOSE_ENV_FILE" ps
```

The default production model contains `db`, `redis`, `api`, `frontend`, and
`edge`. Only Caddy publishes host ports (80/443); API, frontend, PostGIS, and
Redis remain private. PostGIS and Redis attach only to the internal data
network. API, frontend, and optional worker/migration containers also attach to
a non-published egress bridge so runtime HTTPS integrations such as Sentry can
reach the internet without exposing an inbound host port. The worker is
excluded by default. Do not select its
profile against real earnings while Q4/Q5 remain open. If separate written
product authorization is later recorded:

```bash
docker compose --env-file "$COMPOSE_ENV_FILE" --profile worker up -d worker
```

Run the non-destructive release smoke with a pre-existing account. The password
is read from stdin or a protected file, never a command-line argument:

```bash
export SMOKE_BASE_URL=https://staging.example.invalid
read -rsp "Smoke password: " SMOKE_PASSWORD; echo
printf '%s\n' "$SMOKE_PASSWORD" |
  scripts/release_smoke.sh --email smoke-operator@example.invalid --password-stdin
unset SMOKE_PASSWORD
```

The smoke checks the public login page, private API readiness, database
revision, authenticated Redis, and login. It creates no users, campaigns,
payments, or seed data, and discards the login response without printing it.
Normal authentication audit and limiter telemetry are expected.

For backup/restore under this topology, keep `COMPOSE_FILE` and
`COMPOSE_ENV_FILES`/Compose environment configuration pointing at the same
deployment, then run `scripts/db_backup.sh` or `scripts/db_restore.sh`. The
restore script stops the API, frontend, and worker; it restarts the worker only
when that worker was running before restore.

Rollback application code by restoring the previous image tag and recreating
`api`, `frontend`, and `edge`. Roll back data only with the reviewed restore
procedure below. Teardown leaves named data volumes intact:

```bash
docker compose --env-file "$COMPOSE_ENV_FILE" --profile worker --profile release down
```

After an approved final backup and verification, deleting the named volumes is
a separate destructive operation. Never combine it with routine teardown.

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
- Logout deletes only the current device's cookie. It does not revoke other devices.
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

The manifest and service worker are scoped to `/driver`. The forced first-login route `/driver/change-password` stays inside that scope. The shared `/login` route does not: if a driver's session fully expires, a standalone PWA can show browser scope-escape UI until navigation returns below `/driver`. This predates F7 and needs a separate product decision about a driver-scoped login or a wider manifest scope.

## Login rate limiting

Default failure/in-flight thresholds are:

| Bucket | Limit | Window |
|---|---:|---:|
| Normalized account | 5 | 15 minutes |
| Client IP | 150 | 5 minutes |
| Platform global | 250 | 5 minutes |

Successful login deletes the account counter and refunds its IP/global reservation. Redis/Lua errors fail open with a warning so a cache outage cannot lock out all users. The login form presents backend `429` responses and the retry delay.

Password-change attempts share the same buckets so a stolen session cannot brute-force the current password: a wrong current password keeps its reservation and is audited as `auth.password.change_failed`; proving the current password refunds it. Limit transitions appear as `auth.password.change_rate_limited`.

With client-header trust disabled, FastAPI uses its direct socket peer. Browser login calls arrive through the BFF, so they share the Next server's IP bucket. An unauthenticated attacker sustaining roughly 150 junk form submissions per five-minute window can therefore block all web-UI logins; 250 failures fill the global bucket. The per-account bucket remains the primary credential-guessing control in this topology. Repeating `auth.login.rate_limited` records with `bucket=ip` or `bucket=global` in `/admin/audit` identify this condition.

Clear only login limiter keys during an approved lockout response:

```bash
docker compose exec -T redis sh -c "redis-cli --scan --pattern 'ratelimit:login:*' | xargs -r redis-cli DEL"
```

This is temporary relief, not a substitute for blocking the source at the edge. Do not flush unrelated Redis data.

### Trusted-edge preconditions

Do not enable `LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER` until all of these are true:

1. A public reverse proxy is the only client entry point and derives client identity from its accepted TCP socket peer, not from a client-supplied forwarding header.
2. The proxy strips inbound `X-Client-IP` and `X-Forwarded-For`, then overwrites one internal `X-Client-IP` value.
3. Next passes only that proxy-created value through the login action; it never parses `X-Forwarded-For` itself.
4. Both API `8000:8000` and frontend `3100:3000` host mappings are unpublished. Postgres and Redis mappings are also unpublished.
5. `LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS` contains only the BFF container network(s) FastAPI sees as its direct peer. An empty allowlist means trust nobody.
6. A test proves forged direct headers cannot select a limiter bucket and distinct edge socket peers do receive distinct buckets.

If any condition is absent, leave header trust off. The browser-to-API path is `browser → edge → Next/BFF → FastAPI`; FastAPI sees the BFF peer, not the edge peer.

## Post-trip processing worker

The `worker` service runs an arq worker (`arq app.jobs.worker_entry.WorkerSettings`) that completes the pipeline for ended trips: analytics and fraud flags, one current-formula impression estimate, and one current-formula payout calculation plus its ledger entry. It fills missing stages and refreshes an existing impression estimate when its analytics or open-fraud inputs are stale; it never rewrites a historical payout, and old-formula analytics must be recomputed through the admin endpoint. Work arrives two ways: a fail-open enqueue after each trip-end commit, and a periodic sweep that derives due trips from Postgres. The strict entry module rejects a missing `REDIS_URL` before arq constructs a worker or opens a socket.

```bash
docker compose up -d worker
docker compose logs -f worker
docker compose stop worker
```

The worker publishes no host port. Settings: `WORKER_SWEEP_INTERVAL_MINUTES` (default `5`; must be a divisor of 60 between 1 and 60 — anything else fails Settings validation at startup) and `WORKER_SWEEP_BATCH_SIZE` (default `25` trips per sweep).

| Failure | Effect | Recovery |
|---|---|---|
| Redis down at trip end | Trip end still returns 200; API logs a `event=trip_enqueue_failed` warning | Sweep completes the trip within one interval |
| Redis data loss (flush, restart) | Queued jobs lost | Sweep re-derives all due work from Postgres |
| Worker down | Ended trips accumulate unprocessed | Start the worker; sweeps drain the backlog in batches |

Watch for `job=process_trip trip_id=... overall=... stages=...` per enqueued trip and `job=process_unprocessed_trips selected=... processed=... partial=... failed=... skipped=...` per sweep. A non-zero `failed` count, with a stackful log and a Sentry event per failure when a DSN is set, means trips need operator attention. Savepoint convergence handles the six known uniqueness races inside the write services; any integrity error that escapes those services is a real failure and remains visible.

The sweep reads due-work facts only from Postgres and attempts at most one keyset page per occurrence (`WORKER_SWEEP_BATCH_SIZE`, 25 trips by default). Its last `(ended_at, trip_id)` cursor is a disposable Redis traversal hint: the next occurrence resumes at the following page, and a short or empty page clears the cursor so the subsequent occurrence wraps to the oldest due trip. Redis loss merely restarts that traversal; it cannot mark work complete. Therefore a corrupt prefix can consume one occurrence but cannot permanently starve healthy trips behind it.

Positive current-formula payout calculations missing ledger entries are money-invariant repair work. The sweep selects them even when analytics is on an old formula, heals every missing ledger for the trip, and audits all created ledger IDs. Zero, blocked, and insufficient-data calculations remain terminal. Old-formula analytics otherwise blocks impressions and payouts until the admin recompute endpoint writes the configured formula. Downstream rows carry source fingerprints; changed analytics requires an estimate refresh, and a payout whose source fingerprint changed fails clearly with `PAYOUT_CALCULATION_STALE` instead of rewriting historical money.

Each trip run reads one timestamp from the database clock and injects it through analytics, impression, and payout services. This keeps the worker path frozen-time testable and prevents stages in one run from acquiring unrelated application-clock timestamps.

**Transitional money warning.** The automated payout stage runs the existing `payout_v1` engine solely as transitional infrastructure to prove worker orchestration. It is not the approved pilot payment model — D2 specifies hourly pay, and Q4/Q5 are still open. Do not enable this worker against production data or real driver earnings. Production enablement is a separate, explicitly approved delivery.

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
completes it (pending detaches are FINALIZEd first; standalone partition
tables are dropped only when the evidence trail claims them — an
`orphan=... outcome=unclaimed_table` error log means a table the job refuses
to touch: investigate manually).

**Backups respect retention (§24.2.5):** backup rotation must stay ≤ 35
days so purged pings age out of backups automatically — the local
`scripts/db_backup.sh` newest-14 rotation complies at any realistic cadence;
keep any off-host copies on the same bounded rotation.

| Failure | Effect | Recovery |
|---|---|---|
| Worker down for days | Coverage shrinks; `/health/partitions` 503s ~1 month before writes would fail | Start the worker; premake catches up idempotently (4-month horizon ≈ 3 months of headroom) |
| `no partition of relation found for row` on ping insert | Coverage exhausted (both alarms ignored) | Start worker or run premake once; the insert path recovers immediately — no data was lost, the write was rejected |
| Retention crash mid-run | `data_purge_audit` shows the interrupted state | Next daily run recovers (FINALIZE + evidenced-orphan drop); no manual SQL needed |
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

## Secret rotation

Keep secrets in the host/platform secret store, not Git or image layers. Rotate one dependency at a time and retain a tested rollback value until health checks pass.

1. Take a database backup and record the current deployment revision.
2. Rotate the database password in Postgres, update `POSTGRES_PASSWORD` and `DATABASE_URL`, recreate API/database services as required, then check readiness.
3. Configure Redis authentication in the private topology before putting a password into `REDIS_URL`; test limiter degradation and recovery.
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
| Redis unavailable | API warning logs | Login intentionally fails open. Restore Redis and verify every limiter key has a positive TTL. |
| Driver pings stop flushing | Device network, tracker error, 12-hour cap | Keep the app visible, preserve buffered pings, reauthenticate if the absolute cap passed, and retry. |
| Restore stops after a rename | Script's stage/recovery output and database names | Keep writers stopped; follow the exact printed recovery SQL. Never drop the safety database first. |
| Browser Sentry remains silent | Image build arguments | Rebuild with `NEXT_PUBLIC_SENTRY_DSN`; a container restart is insufficient. |
| Local e2e assertions drift | Persistent demo/e2e records | Reset only the intended local Compose volumes, reseed, and rerun with test rate limits. |
