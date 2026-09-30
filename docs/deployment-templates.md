# Deployment templates — Render, AWS S3 with KMS, ClamAV, Postmark, Mapbox

**Status: templates only (REQ-010). Not deploy-ready.** Nothing here has been applied: no
account, service, bucket, key, DNS record or provider call exists. Applying any template creates
billable resources and needs the owner's written approval, in accounts Terrax Media owns with the
developer invited (REQ-028). The domain is still to be confirmed (REQ-033).

| File | What it is |
| --- | --- |
| [`deploy/render/render.yaml`](../deploy/render/render.yaml) | Render Blueprint: private API, worker, public frontend, private ClamAV, Postgres, Key Value |
| [`deploy/aws/s3-kms-iam-policy.json`](../deploy/aws/s3-kms-iam-policy.json) | Least-privilege IAM policy for the app's S3 user and the bucket's KMS key |
| [`deploy/aws/s3-cors.json`](../deploy/aws/s3-cors.json) | Bucket CORS for browser uploads (presigned POST) and downloads |
| [`tests/test_deploy_templates.py`](../tests/test_deploy_templates.py) | Keeps the templates valid: known setting names, no committed secrets, switches off, exact IAM actions |

The providers are the client's choices (client answers items 9–16, 24 Sep 2026): Render hosting,
the hosting provider's AWS storage and encryption, ClamAV, Postmark from support@terraxmedia.com,
Mapbox now and Google Maps later, domain terraxmedia.com.

## Go-live gaps these templates do not close

Each needs its own reviewed change before a real deployment. They are listed first so the
templates are never mistaken for a working setup.

1. **No security edge on Render.** In the reviewed topology Caddy (`Caddyfile`) sets the
   Content-Security-Policy and other security headers, strips forged forwarding headers and sets
   `X-Client-IP`. Render has no Caddy, so none of that happens. Options: run a Render-specific
   Caddy service as the only public entry, or move the headers into Next.js.
2. **Webhooks and health checks cannot reach the private API.** Caddy routes `/api/v1/webhooks/*`
   and the health paths straight to the API; everything else goes to the frontend. With a private
   API and no Caddy, Paystack webhooks (`W2-01C`) and external health checks have no route in.
   The same edge decision as gap 1 fixes this.
3. **Redis TLS — as written, the API, worker and migrations will not start.** Settings require
   `rediss://` with a password outside local/test, and `alembic/env.py` loads the same settings.
   Render Key Value's internal address is, as far as we know, plain `redis://` without a password
   (not verified against Render's docs). Until a TLS, password-protected Redis is chosen (another
   provider, or a decision to relax the rule for a private network), this template cannot run.
4. **Database URL form.** Settings require `postgresql+asyncpg://…?ssl=require` (or `verify-ca` /
   `verify-full`), so Render's generated connection string cannot be used as it is. Enter
   `DATABASE_URL` by hand in that form. Confirm the `postgis` extension is available on the chosen
   Postgres plan before creating anything.
5. **Mapbox is not verified with our map library.** The frontend uses MapLibre GL. Mapbox styles
   refer to `mapbox://` sources, sprites and glyphs, which MapLibre does not resolve without a
   request transform, and Mapbox's terms may limit its tiles to Mapbox's own SDKs. The CSP also
   does not yet allow Mapbox origins. Treat Mapbox as needing a code change and a terms check.
6. **Release scripts are for Docker Compose.** `scripts/release.sh` and `release_contract.py`
   drive the self-hosted topology and stop on managed data
   (`MANAGED_DATA_RELEASE_ADAPTER_REQUIRED`). On Render the Blueprint's
   `preDeployCommand: alembic upgrade head` runs migrations. Backups, restore checks and smoke
   tests need Render-specific procedures.
7. **Encryption keys are not held in AWS KMS.** Bank details and NINs use envelope encryption with
   a key ring supplied as `PAYOUT_CRYPTO_KEYRING_B64`. A KMS custody backend is not built
   (`EXT-KMS-CUSTODY`). KMS here only encrypts the S3 bucket.
8. **Long-lived AWS access key.** Render cannot assume AWS IAM roles, so the app uses an IAM user's
   access key. Rotate it on a schedule and after any staff change.
9. **File retention is unresolved.** The client asked for "keep old files 6 months", but KYC and
   money records have legal retention needs (client answers items 11 and 17, REQ-032). No
   lifecycle rule is included, and `FILE_KYC_RETENTION_DAYS` stays blank.
10. **ClamAV sizing is unverified.** clamd reaches about 3 GB while reloading signatures, so the
    template uses the 4 GB `pro` plan. It has no disk, so it downloads signatures on every start,
    and the signature servers sometimes rate-limit cloud addresses. Check start-up on Render.
11. **Client-IP trust stays off, so login limits are shared by everyone.** With
    `LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER` false the API sees every request as coming from the
    frontend's internal address. The per-address login limit (150 failures in 5 minutes) and the
    password-reset limit (10 an hour) therefore become one bucket for the whole platform: one
    attacker, or ordinary traffic, can block login or password reset for everyone. This is fixed
    only with the trusted edge from gap 1 (see `docs/staging-options.md`).
12. **Where personal data is stored is not decided.** The client left the hosting and storage
    region to the developer (client answers items 10–11), and the template proposes Render
    `frankfurt` and an EU S3 region as the closest to Nigeria. Storing Nigerian drivers' identity,
    bank, KYC and location data abroad is a data-protection (NDPA) decision that needs the owner's
    written approval and Terrax's legal adviser (REQ-032); `docs/staging-options.md` already
    requires approval of region and data residency.
13. **`sync: false` inside an environment group is unconfirmed.** If Render refuses it when the
    Blueprint is applied, enter the secrets in the group through the dashboard instead, or move
    them to each service's own `envVars`.

## Render

The Blueprint defines one shared environment group for the API and worker, plus the frontend's own
variables. Region `frankfurt` is the developer's proposal, pending gap 12. `ENVIRONMENT=staging`
is for the private test website; change it to `production` only for the live site.

Secret formats (generate fresh values, never reuse local ones):

- `JWT_SECRET_KEY`: at least 32 random characters.
- `PAYOUT_CRYPTO_KEYRING_B64` and `TRIP_EVIDENCE_SIGNING_KEYRING_B64`: despite the name, a JSON
  object mapping a positive version to a base64-encoded 32-byte key, for example
  `{"1":"<base64 of 32 random bytes>"}`, with the matching `*_KEY_VERSION`. Both are needed:
  without the trip-evidence key ring the readiness check reports `not_configured`.
- `EMAIL_RECEIPT_SIGNING_SECRET`: at least 32 characters.
- `DATABASE_URL`: `postgresql+asyncpg://user:password@host:5432/db?ssl=require` (`ssl=require`
  encrypts without checking the certificate; `verify-full` needs a CA bundle).
- `REDIS_URL`: `rediss://:password@host:port` (see gap 3).

Setup order, once approved and gaps 1–4, 11 and 12 are decided:

1. In the Terrax-owned Render account, create the Blueprint from `deploy/render/render.yaml`.
2. Enter every `sync: false` value when Render asks. Generate fresh secrets; never reuse local ones.
3. After the API service exists, set the frontend's `API_BASE_URL` to
   `http://<API internal host>:8000` and `PUBLIC_ORIGIN` to the confirmed app address.
4. Deploy. Render builds the frontend image with `NEXT_PUBLIC_*` values, so changing them needs
   a rebuild.

Values that stay blank or off until the client answers: Paystack key (REQ-027), invoice issuer
reference (the accountant's sign-off, D42), daily-rate pay publishing (REQ-014 to REQ-016),
automatic payouts (REQ-017, REQ-029, REQ-030), budget policy, privacy and measurement live flags
(REQ-032), KYC retention, driver registration, demo seed and demo login.

## AWS S3 with KMS

1. In the Terrax-owned AWS account, create a customer-managed KMS key for the bucket.
2. Create a private bucket in the chosen region: Block Public Access on, versioning on, default
   encryption SSE-KMS with that key and S3 Bucket Keys enabled. Do not add a bucket policy that
   demands an encryption header: the app relies on the default encryption.
3. Apply `deploy/aws/s3-cors.json` with the confirmed app origin (and the staging address too, if
   staging runs before the domain is confirmed). When security headers are added (gap 1), the
   CSP `connect-src` must include the S3 origin, as the Caddy version does.
4. Create an IAM user for the app, attach `deploy/aws/s3-kms-iam-policy.json` with the bucket, key,
   region and account filled in, and create one access key. The KMS permission only works through
   S3 (`kms:ViaService`); the key's own policy must allow IAM policies to grant access (the
   default key policy does).
5. Optional: a lifecycle rule limited to the `release-canary/` prefix, expiring noncurrent
   versions after a day. The readiness probe writes and deletes a canary object there, and with
   versioning on each probe leaves an old version behind. This does not touch the retention
   question in gap 9.
6. Set `OBJECT_STORAGE_ENDPOINT_URL` and `OBJECT_STORAGE_PUBLIC_ENDPOINT_URL` to
   `https://s3.<region>.amazonaws.com`, plus `OBJECT_STORAGE_REGION`, `OBJECT_STORAGE_BUCKET` and
   the access key pair.

The IAM actions are exactly what `app/adapters/storage/s3.py` uses: get, put, copy and delete
objects and object versions, list versions (`s3:ListBucket` also turns a missing key into "not
found" rather than "access denied"), and `kms:GenerateDataKey` / `kms:Decrypt` for the bucket key.
Upload checks use SHA-256 over the stored bytes, so SSE-KMS does not affect them.

## ClamAV

The Blueprint runs the official `clamav/clamav` image as a private service on port 3310, and the
backend reaches it through `MALWARE_SCANNER_HOST`. Pin the image by digest before use. The client
approved ClamAV and left file types and sizes to the developer (client answers item 12); the
per-purpose limits are in client-decisions "File uploads".

## Postmark

`EMAIL_PROVIDER=smtp` with `smtp.postmarkapp.com`, port 587 and STARTTLS. The SMTP username and
password are both the Postmark server token. Sender `support@terraxmedia.com` (client answers item
14) works only after the terraxmedia.com domain is verified in Postmark (DKIM and Return-Path DNS
records), which needs the domain access the client approved. `EMAIL_RECEIPT_SIGNING_SECRET` is
Cardvert's own delivery-receipt key (32 characters or more), not a Postmark value.

## Mapbox

`NEXT_PUBLIC_MAP_STYLE_URL` is the only map setting. It is baked in at build time. It would hold
a Mapbox style URL with a public token restricted to the app's domain. Gap 5 applies: the pairing
of MapLibre and Mapbox styles, the CSP and Mapbox's terms must be settled first. Until then the
app shows its built-in schematic map.

## Invoice issuer details (D42)

Real invoices need an issuer profile recorded through `POST /api/v1/admin/invoice-issuer-profiles`
**and** the accountant's sign-off, recorded as `INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE`. While
that setting is blank, a verified profile is refused and no real invoice can be issued. A verified
profile also needs every one of: legal name, address, RC number, TIN, phone, email, bank name,
account name and account number.

Known today (client-decisions "Invoices and VAT"): Terrax Media Company Ltd, 73 Lome Crescent,
Wuse Zone 7, FCT Abuja, 07074200080, terraxmediacompany@gmail.com. Still missing: which of RC or
TIN the number 2521515778093 is, and the other number (REQ-019); Terrax's OPay bank details; the
invoice-number prefix; the accountant's confirmation. Never enter a guessed RC, TIN or bank value.
