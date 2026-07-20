# Staging hosting options — research only

Pricing checked **12 July 2026** against the linked provider pages. Estimates exclude VAT, domain registration, excess bandwidth, support plans, and exchange-rate movement. They are sizing sketches, not quotes.

**Gate:** do not create an account, buy a service, change DNS, or deploy until OJ gives written approval.

## Shared requirements for every option

- Public traffic terminates TLS at one controlled edge and reaches the Next.js BFF. API, PostGIS, and Redis stay private.
- Run `alembic upgrade head` as a one-shot release step before starting new API code. Do not automatically run the demo seed.
- Set `ENVIRONMENT=staging`. The seed explicitly treats staging as production-like and refuses to run even when `ALLOW_DEMO_SEED=true`; changing that policy requires written approval and a disposable database.
- Server settings, including `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, and `SENTRY_DSN`, are runtime secrets. `NEXT_PUBLIC_SENTRY_DSN` is a frontend build-time argument; changing it requires a rebuild.
- Persist `pg_dump -Fc` backups outside the database's writable volume and rehearse restore. Provider snapshots complement, but do not replace, application-level dumps.
- Before trusting a forwarded client IP, apply the trusted-edge checklist below.

## Option 1 — Hetzner Cloud VPS with Docker Compose

### Topology and estimated monthly cost

One Europe-region `CX33` VM runs Caddy, frontend, API, PostGIS, and Redis on a private Compose network. Only Caddy publishes 80/443. A small external object-storage target or separately mounted backup destination holds encrypted dumps.

| Component | Estimate |
|---|---:|
| CX33, 4 vCPU / 8 GB class | €8.49/month excluding IPv4 and VAT |
| Backup storage/traffic | provider- and retention-dependent; budget €1–5 |
| Estimated base | **about €10–14/month**, plus IPv4/VAT/domain |

Source: Hetzner's [15 June 2026 cloud price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) lists the Germany/Finland CX33 at €8.49/month excluding IPv4 and VAT. Recheck the live console before approval.

### Setup steps

1. Provision a CX33 in the closest acceptable European region; enable provider firewall rules for SSH from operator IPs and public 80/443 only.
2. Install Docker Engine and the Compose plugin; create a non-root deploy user and disable password SSH.
3. Point an `A`/`AAAA` record such as `staging.example.com` at the VM. Configure Caddy to obtain/renew Let's Encrypt TLS and proxy only to `frontend:3000`.
4. Create a production override that removes all host `ports` mappings from frontend, API, Postgres, and Redis. Do not bind `8000`, `3100`, `5432/5433/5434`, or `6379` even to a public firewall-protected interface.
5. Store runtime secrets in a root-readable environment file outside Git. Pass `NEXT_PUBLIC_SENTRY_DSN` only during `docker compose build frontend`.
6. Start PostGIS/Redis privately, run `docker compose run --rm api alembic upgrade head`, then start API/frontend and verify health through Caddy.
7. Schedule `scripts/db_backup.sh`; encrypt and copy selected dumps off the VM. Provider snapshots do not replace dumps. Record a restore rehearsal.
8. Test that direct frontend/API connections fail, forged forwarding headers are replaced, and separate edge socket peers create separate limiter buckets before enabling trusted-client-IP mode.

### Teardown and rollback

Rollback application code by pinning the previous image/revision; restore the pre-migration dump if schema rollback is not demonstrably safe. To tear down, first export and verify the final dump, remove DNS, revoke TLS/secrets, then destroy volumes and the VM. Confirm detached storage and snapshots are also removed to stop billing.

**Fit:** cheapest and closest to the current Compose topology, but patching, backups, monitoring, and single-host failure recovery are operator responsibilities.

## Option 2 — Render managed services

### Topology and estimated monthly cost

Use two Docker web services (frontend public, API either private or restricted to frontend), managed Render Postgres with PostGIS confirmed before purchase, and persistent Render Key Value. Render terminates TLS for the custom domain and provides private networking.

| Component | Pilot size | Cost |
|---|---|---:|
| Frontend web service | Starter, 512 MB | $7/month |
| API service | Starter, 512 MB | $7/month |
| Postgres | Basic 1 GB | $19/month + storage |
| Key Value | Starter, persistent | $10/month |
| Estimated base | | **$43/month + Postgres storage/bandwidth** |

Source: Render's [current pricing](https://render.com/pricing) lists Starter services at $7, Basic-1gb Postgres at $19, Starter Key Value at $10, Postgres storage at $0.30/GB, and automatic TLS/private networking. Free Postgres expires after 30 days and free Key Value is not persistent, so neither is suitable for durable staging.

### Setup steps

1. Confirm the selected Render Postgres plan/region permits the required `postgis` extension before creating anything.
2. Define separate frontend/API Docker services from the monorepo. Expose only frontend publicly; use Render private service discovery or a narrowly restricted API origin.
3. Add the staging custom domain to the frontend and let Render issue TLS. Point DNS only after the provider hostname passes health checks.
4. Put server secrets in Render environment groups. Supply `NEXT_PUBLIC_SENTRY_DSN` to the frontend build environment, while `SENTRY_DSN` remains runtime configuration.
5. Attach managed Postgres/Key Value private URLs. Run `alembic upgrade head` as a pre-deploy job using the direct database URL, not a transaction-pooling URL.
6. Leave demo seeding disabled. If client-approved sample data is later needed, use an explicit one-shot job against a database identified as disposable.
7. Store scheduled custom-format dumps in external encrypted object storage. Render's paid Postgres recovery is useful, but portability still requires tested dumps.
8. Leave trusted-client-IP mode disabled unless Render's documented edge semantics or an added private reverse-proxy service can satisfy every stripping, socket-peer, unpublish, and test condition below. Do not treat an arbitrary `X-Forwarded-For` value as equivalent.

### Teardown and rollback

Use Render's retained prior build for application rollback. For schema/data rollback, restore the verified dump into a replacement database and repoint services after validation. Before teardown, export the final dump, remove DNS, suspend services, delete Key Value/Postgres, and verify no persistent disk or database remains billable.

**Fit:** lower operational burden and straightforward TLS, but materially more expensive than a single VPS. Confirm PostGIS and private API topology in a no-purchase design review.

## Option 3 — Fly.io Machines

### Topology and estimated monthly cost

For a cheap, non-production staging pilot, run frontend and API as private-networked Machines, plus self-managed PostGIS and Redis Machines with Fly volumes in one European region. Only the frontend app receives public routing/TLS. This uses Fly's **unsupported unmanaged Postgres** path; managed Postgres is safer but starts at $38/month plus storage.

| Component | Example size | Cost |
|---|---|---:|
| Frontend Machine | shared-cpu-1x, 512 MB | $3.32/month |
| API Machine | shared-cpu-1x, 512 MB | $3.32/month |
| PostGIS Machine | shared-cpu-1x, 1 GB | $5.92/month |
| Redis Machine | shared-cpu-1x, 256 MB | $2.02/month |
| Volumes | 16 GB total example | $2.40/month |
| Estimated base | | **about $17/month**, plus egress/snapshots |

Sources: Fly's [resource pricing](https://fly.io/docs/about/pricing/) lists those shared-Machine prices, volumes at $0.15/GB/month, and snapshots at $0.08/GB/month after the first 10 GB. Fly explicitly labels [unmanaged Fly Postgres](https://fly.io/docs/postgres/) unsupported. Supported [Managed Postgres](https://fly.io/docs/mpg/) includes PostGIS and starts at $38/month plus $0.28/GB, making the otherwise equivalent managed topology roughly $50+/month.

### Setup steps

1. Choose one European region and create distinct apps/Machines for frontend, API, PostGIS, and Redis. Attach volumes to data services and keep them on Fly private networking.
2. Allocate public routing only to the frontend. Configure the custom domain and Fly-managed certificate, then add DNS records after certificate validation instructions are known.
3. Set runtime secrets with the platform secret store. Build the frontend image with `NEXT_PUBLIC_SENTRY_DSN`; set server `SENTRY_DSN` at runtime.
4. Enable PostGIS, use private database/cache addresses, and run a one-shot API Machine with `alembic upgrade head` before rolling application Machines.
5. Keep staging seed disabled. Scale Machines deliberately; never allow the database Machine to scale to zero.
6. Write encrypted dumps to a dedicated backup volume and copy critical dumps outside the Postgres Machine/region. Treat Fly snapshots as a second recovery layer, not the only backup.
7. Leave trusted-client-IP mode disabled unless an owned edge Machine is the only entry point and its socket peer is demonstrably the client (or Fly's documented trusted-proxy chain is explicitly validated). The default Fly proxy peer alone is not the client IP.

### Teardown and rollback

Rollback by releasing the previous image to API/frontend Machines. Restore data into a replacement PostGIS Machine/volume and switch the private connection only after validation. On teardown, export a final dump, remove DNS/certificates, destroy every Machine, then separately delete volumes, snapshots, apps, and any managed database/Upstash extension; deleting an app does not necessarily delete its database resources.

**Fit:** low compute cost and flexible private networking, but the cheap estimate shifts database operations and recovery onto the team. Prefer managed Postgres if the extra monthly cost is acceptable.

## Trusted client-IP edge design

The public edge must remove both inbound `X-Client-IP` and `X-Forwarded-For` and overwrite a single internal `X-Client-IP` from the accepted socket peer. It must never trust the first value sent by the browser. Next's login action relays only that edge-created header; FastAPI honors it only when all three settings are configured:

- `LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER=true` on Next;
- `LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER=true`; and
- FastAPI's direct `request.client.host` belongs to `LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS`.

The allowlist contains the internal BFF/Next peer CIDR, because the request path is `client → edge → Next → FastAPI`; it does not contain an assumed browser or edge address. Empty means no trusted proxy.

Before enabling trust, unpublish **both** frontend `3100:3000` and API `8000:8000` mappings, along with database/cache mappings. Otherwise an attacker can bypass the stripping edge, send a forged header directly to Next, and have the allowlisted BFF relay it. Verify from outside the private network that only 80/443 are reachable, then test forged-header rejection and distinct real client buckets.

Illustrative Caddy intent (validate against the selected deployment and Caddy version before use):

```caddyfile
staging.example.com {
    # Ignore client forwarding headers; derive the internal value from the
    # connection peer accepted by this edge.
    request_header -X-Client-IP
    request_header -X-Forwarded-For
    request_header X-Client-IP {remote_host}
    reverse_proxy frontend:3000
}
```

If the provider places another load balancer in front, `{remote_host}` may be the provider proxy rather than the client. Use only that provider's documented trusted-proxy mechanism and test it; otherwise leave client-header trust disabled and accept the shared-BFF IP bucket documented in the runbook.

## Recommendation for client review

- Choose **Hetzner Compose** for the lowest cost and fastest parity with local operation, provided one named operator owns patching and off-host backups.
- Choose **Render** when reduced operations work is worth roughly $43+/month and PostGIS is confirmed.
- Choose **Fly Machines** only with explicit acceptance of unsupported self-managed Postgres, or revise the budget upward for Fly Managed Postgres.

No option should proceed past research until OJ's written approval records the selected provider, region/data residency, budget ceiling, operator, backup destination, and trusted-edge design.
