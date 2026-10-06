# Deployment templates — Hetzner, MapTiler, ClamAV and Postmark

**Templates only (D44/D65, REQ-049/117). Not deployed or provider-verified.**
No accounts, servers, buckets, keys or DNS records were created. Every secret
is blank. Applying anything needs separate owner approval in Terrax-owned
accounts (REQ-050); app address remains REQ-033/043 and legal residency REQ-032.

| Artifact | Purpose |
| --- | --- |
| `production.env.example`, `staging.env.example` | Complete release settings; secrets, map key and budget ratios blank |
| `docker-compose.production.yml`, `Caddyfile` | Standalone pinned-image release; sole public TLS edge, private API/worker/PostGIS/Redis/ClamAV |
| [Hetzner notes](../deploy/hetzner/README.md) | Provider binding and operational gates |
| [Hetzner S3 CORS](../deploy/hetzner/s3-cors.json) | Exact approved browser origin, GET/POST presigned access |
| `tests/test_deploy_templates.py` | Blank secrets, disabled policies, narrow CSP and scanner contract |

Render Blueprint, AWS IAM/KMS and Mapbox instructions have been removed.
Postmark stays; bank/NIN encryption uses Cardvert's supplied key ring, not a
provider KMS. No region or recurring-spend choice is made here.

## Disposition of Batch F's 13 gaps

“Falls away” means a superseded template mismatch, never live deployment proof.

| Gap | W1B disposition | Remaining evidence/action |
| --- | --- | --- |
| 1 — no Render security edge | Falls away: existing Caddy sole entry and security/forwarding headers | Approved public-edge security rehearsal |
| 2 — private webhooks/health unreachable | Falls away: existing Caddy health/webhook routes | Public webhook delivery/recovery under W2-01C |
| 3 — Render Redis plaintext/auth mismatch | Falls away: authenticated TLS-only bundled Redis | Certificates, release smoke and restore evidence |
| 4 — generated database URL/PostGIS | Falls away: pinned bundled PostGIS and explicit asyncpg verified TLS | External TLS inputs and deployment proof |
| 5 — Mapbox/MapLibre and CSP | Template mismatch closes: MapTiler HTTPS styles and narrow API CSP | Account/licence, restricted public key, real tile/sprite/glyph browser rehearsal |
| 6 — Render release lifecycle | Falls away: existing standalone Compose release/backup/restore/recovery | Host rehearsal, off-host backup scheduling, restore/compatibility evidence |
| 7 — application keys outside AWS KMS | Still open: D44 key ring remains; no KMS claim | Production custodian, injection, rotation/recovery, EXT-KMS-CUSTODY |
| 8 — long-lived AWS key | AWS-specific mismatch falls away; Hetzner credentials remain long lived | Dedicated project or reviewed per-key bucket policy, injection and rotation |
| 9 — retention | Still open | REQ-032 legal retention/DSR; FILE_KYC_RETENTION_DAYS blank |
| 10 — ClamAV sizing/startup | Partly addressed: private service, 4 GiB, persistent signatures, update egress and health dependencies | Approved image/host capacity, cold start/reload, signature updates and outage/EICAR rehearsal |
| 11 — shared login bucket without edge | Falls away: exact Caddy/BFF trust topology in both examples | Public peer/forgery/limiter rehearsal |
| 12 — personal-data region | Still open | REQ-032 legal decision for server/storage/processors; no Europe/US choice |
| 13 — Render sync:false syntax | Falls away: no Blueprint or environment group |

## Hetzner release binding

Use the **standalone** production Compose file; do not merge local Compose into
it. Copy an env example to a protected file outside Git, inject secrets,
approved image digests, certificates and domain, then validate with
`docker compose -f docker-compose.production.yml --env-file <protected-file> config`.
Blank secrets prevent operational rendering; synthetic stand-ins exist only
in tests. Never start a release from the examples.

Postgres uses `postgresql+asyncpg://...@db:5432/mobility?ssl=verify-full` with the
supplied CA. Redis uses authenticated `rediss://...@redis:6379/0` with
`ssl_ca_certs=/run/secrets/redis_tls_ca&ssl_cert_reqs=required`. Certificate SANs
must match db/redis. Managed data still fails with
`MANAGED_DATA_RELEASE_ADAPTER_REQUIRED`; no managed adapter is introduced.

Supply approved immutable `CLAMAV_IMAGE` from the official image family
supporting `clamdcheck.sh`. The locally inspected 1.4 image metadata confirms
that command and 360-second start period; no registry call/pull was made.
ClamAV has private data-network access, update egress, no host port,
`clamav_signatures` persistence, 4 GiB limit and restart policy. API and worker
await health; upload/readiness scanning remains fail closed. The host needs
**at least 8 GB RAM** because ClamAV alone is capped at 4 GB, with the remaining
memory needed by the database, API, worker, frontend and host. The
[ClamAV Docker guide](https://docs.clamav.net/manual/Installing/Docker.html)
explains memory and signature persistence. Release and recovery scripts wait up to
900 seconds for the scanner and application services to become healthy,
covering the scanner's 360-second start period and health retries. A scanner
that remains unhealthy fails the release before readiness and public edge
startup. Never relax readiness to bypass an unhealthy scanner.

`WEB_CONCURRENCY=2` matches the image default and is passed explicitly to
Uvicorn; operators can configure it. Worker job concurrency is separate.
Only Caddy publishes 80/443. Use existing `scripts/release.sh`,
`backup_release.sh`, `verify_restore.sh`, `recover_release.sh` after separately
approved provisioning, with immutable images built away from the host and
signed compatibility evidence. No migration/automatic seed is added here.

## Private Hetzner Object Storage

Keep the bucket private and verify versioning for backup/restore. Supply both
endpoint settings as `https://<approved-location>.your-objectstorage.com`,
location as region and bucket separately. The existing adapter signs
path-style URLs: do not use bucket-prefixed endpoints.
[Hetzner endpoint documentation](https://docs.hetzner.com/storage/object-storage/overview/)
describes the S3 service.

Replace the exact app origin in CORS, adding an exact staging origin only if
approved. CORS grants no public object access. GET/POST cover existing
presigned downloads/uploads, including checksum metadata.
[Hetzner CORS instructions](https://docs.hetzner.com/storage/object-storage/howto-protect-objects/cors/)
use S3-compatible tools; no configuration is applied in this task.

Keys default to every bucket in their project. Isolate the application in a
dedicated project or review a per-key bucket policy before provisioning;
AWS IAM restrictions do not apply. See
[Hetzner credential controls](https://docs.hetzner.com/storage/object-storage/faq/s3-credentials/).
Actual checksum upload/versioned read/copy/delete, unsigned denial, backup and
isolated restore remain provider adoption checks. No lifecycle expiry is
selected while legal retention remains unresolved.

## MapTiler with existing MapLibre

Set build-time `NEXT_PUBLIC_MAP_STYLE_URL` to
`https://api.maptiler.com/maps/<approved-map>/style.json?key=<restricted-public-key>`.
The complete URL passes directly to MapLibre without a Mapbox transform.
[MapTiler's MapLibre guide](https://docs.maptiler.com/maplibre/)
documents this HTTPS form. Choose map/account/licence later; no key is committed.
Restrict the browser-visible key to approved origins and rebuild when it
changes. Blank retains the local schematic.

Caddy permits only `https://api.maptiler.com` in connect-src and img-src for
styles, tiles, glyphs and sprites; scripts/fonts/frames gain no origins. No
external SDK/CDN is introduced. Custom styles importing other origins need
review, not wildcard CSP. Rendering, attribution/licence and quota remain
EXT-BASEMAP adoption evidence.

## Email, key custody and unanswered inputs

Postmark SMTP configuration stays explicit, credentials blank. Verify
support@terraxmedia.com and message copy before delivery. Inject JWT, payout
and trip key rings, email receipt and dedicated release evidence secrets
externally. Key rings map positive versions to base64 32-byte keys; retain
required versions for existing ciphertext/evidence. No rotation or account
reconnection is authorized here.

Budget ratios/approval, publishing/automatic payout switches, invoice issuer
sign-off, retention and unresolved evidence policies stay blank/off. Never
substitute template values for client/legal answers. D43 supplied TIN
2521515778093 and RC 8688553; real issuance still needs OPay bank details and
accountant confirmation (D42, REQ-041/042). External payment, deployment,
legal, device and pilot gates remain unchanged.

W1B identifiers renumbered at merge on 2026-10-06: Compose REQ-108 → REQ-117, wording REQ-112 → REQ-116, D62 → D65, architecture v1.117 → v1.122. Master identifiers retain their meanings.
