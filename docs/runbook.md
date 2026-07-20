# Mobility operations runbook

This runbook covers the Docker Compose pilot stack. Run commands from the repository root. Production-like environments must replace local credentials, keep Postgres and Redis private, and put the frontend behind a trusted TLS edge.

## Stack overview

| Component | Compose service | Internal address | Purpose |
|---|---|---|---|
| Next.js BFF | `frontend` (`full` profile) | `frontend:3000` | Browser entry point and httpOnly session-cookie owner |
| FastAPI | `api` | `api:8000` | API, auth, analytics, fraud, and payouts |
| PostGIS | `db` | `db:5432` | System of record |
| Redis | `redis` | `redis:6379` | Login-rate-limit counters |

Local port mappings are development conveniences. Do not expose API `8000`, frontend `3100`, Postgres, or Redis on a public host. Staging should expose only ports 80/443 on the reverse proxy.

Basic checks:

```bash
docker compose ps
docker compose logs --tail=100 api frontend db redis
docker compose exec -T api python -c 'from urllib.request import urlopen; print(urlopen("http://127.0.0.1:8000/api/v1/health", timeout=3).read().decode())'
```

Never stop or kill a process on host port 3000 while operating this repository; it may belong to another project.

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
2. The script captures the checked-out Alembic head, then stops API/frontend writers.
3. It restores and validates `mobility_restore_tmp`.
4. It renames live `mobility` to `mobility_pre_restore_<UTC timestamp>` and the temporary database to `mobility`.
5. With `--upgrade`, it migrates the restored database to the checked-out head.
6. It starts the API, restores the frontend's previous running state, and polls the API health endpoint for up to 40 seconds.

On a failure before the first rename, the script removes the temporary database and restarts the application; the live database is untouched. If only the first rename completed, it renames the safety database back automatically. If a post-swap migration, restart, or health check fails, it retains the failed restored database as `mobility_failed_restore_<timestamp>` and swaps the original back. The error output names the stage and prints exact recovery or pruning commands. If automatic recovery itself fails, keep application writers stopped and follow the SQL printed by the script from a `psql` session connected to `postgres`.

After application and data verification, prune the retained safety database using the exact command printed by the script, for example:

```bash
docker compose exec -T db dropdb -U mobility mobility_pre_restore_yyyymmddthhmmssz
```

Restore rehearsal before release:

1. Take a backup and record a known row.
2. Change or delete that row in a disposable environment.
3. Restore the valid dump and confirm the row and `/admin` return.
4. Make a disposable truncated copy with `head -c 10000`; confirm restore fails at `pre-validate` without stopping the stack.

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
