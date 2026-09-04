---
source_surface: Codex
conversation_id: 01a05c2c-7875-7d11-9bf1-f6459bdb3fba
displayed_title: Audit Cardvert Production Readiness
actual_model: gpt-5.6-sol
reasoning_effort: xhigh
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete final answer
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit Cardvert Production Readiness

> Preserved final answer. It is source evidence, not an accepted finding or
> remediation decision.

## Verdict

**B — substantial deployment foundation, but material production-readiness gaps. NO-GO for a live Cardvert deployment or pilot.**

The audited branch currently points to the requested SHA, and the [exact GitHub commit is `637841d95493bcc24334356da42097fa53a5d16f`](https://github.com/oluwasolaonigbinde/mobility/commit/637841d95493bcc24334356da42097fa53a5d16f). I did not inspect master as a substitute.

External accounts alone are insufficient. Payment, disbursement, advertising-platform activation and production KMS custody still require repository implementation. Recovery compatibility, ongoing readiness and the exact revision’s test/CI status also prevent admission.

An infrastructure-only, provider-neutral staging environment is plausible after remediation. It would not constitute production or pilot readiness. The repository itself correctly marks Packages 3, 8 and 9 as blocked and explicitly says training, live staging, pilot and handover have not happened ([progress lines 61–81](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/progress.md#L61-L81)).

## Deployment dependency graph

```text
Repository remediation + green exact-SHA CI
        |
        +--> Named operations/security/privacy/money owners
        |
        +--> Legal, commercial, evidence, reporting and permit approvals
        |
        +--> Provider selections and sandbox specifications
                    |
                    +--> Payment + disbursement + settlement bank
                    +--> Storage + scanner + KMS
                    +--> Email + phone
                    +--> Basemap + ad platform
        |
        v
Immutable images labelled with exact revision
        |
        v
Isolated staging domain/account/secrets
        |
        +--> PostGIS at exact migration head
        +--> Redis + same-revision worker
        +--> Private versioned object storage
        +--> Scanner/KMS/provider sandbox readiness
        |
        v
Preflight -> off-host backup -> isolated restore -> migration
        |
        v
Current-image readiness + mechanically proven previous-image compatibility
        |
        v
Authenticated smoke + money/privacy/provider/queue E2E
        |
        v
Physical-device, route and battery validation
        |
        v
All six pilot gates PASS -> training rehearsal -> controlled pilot -> handover
```

## Confirmed repository defects

| Priority | Finding | Exact evidence and impact |
|---|---|---|
| P0 | **Live-provider code is absent, not merely unconfigured.** | Billing always returns `DisabledPaymentGatewayAdapter` ([billing.py lines 101–102](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/api/v1/billing.py#L101-L102)); disbursement always returns its disabled adapter ([disbursements.py lines 35–36](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/api/v1/disbursements.py#L35-L36)); ad-platform construction states no environment value can enable a provider ([audience_delivery.py lines 102–105](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/audience_delivery.py#L102-L105)). Provider credentials cannot activate these paths. |
| P0 | **Production KMS/vault custody has no implementation.** | KYC constructs the envelope provider from an in-process keyring ([kyc.py lines 38–42](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/api/v1/kyc.py#L38-L42)); the only custody backend is expressly “Local/test” ([envelope.py lines 155–164](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/adapters/crypto/envelope.py#L155-L164)). Production currently requires a raw keyring secret rather than KMS operations. |
| P1 | **HTTP readiness can report healthy prematurely.** | `/ready` returns HTTP 200 when the database is not configured and otherwise checks connectivity only ([health.py lines 33–60](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/api/v1/health.py#L33-L60)). It does not verify Alembic head, PostGIS, Redis, worker, storage or scanner. Compose uses this endpoint as API health, while edge startup does not depend on worker health ([production Compose lines 172–205 and 244–269](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docker-compose.production.yml#L172-L269)). |
| P1 | **Rollback compatibility is asserted rather than generated.** | Validation accepts a JSON object containing boolean `true` claims for previous-image readiness and report-schema compatibility ([release_contract.py lines 381–433](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/release_contract.py#L381-L433)). The rehearsal manufactures those booleans directly ([rehearse_w403a.sh lines 188–200](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/rehearse_w403a.sh#L188-L200)). Recovery starts the old image against the forward schema but does not execute the claimed previous-image report canary before traffic. |
| P1 | **Redis failure disables brute-force protection without failing readiness.** | The login rate limiter catches Redis failures and returns `allowed=True` ([rate_limit.py lines 149–178](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/core/rate_limit.py#L149-L178)). Combined with readiness ignoring Redis, an outage can leave login “healthy” but degraded open. |
| P1 | **The exact SHA is not a green release candidate.** | GitHub reports [zero check runs for the commit](https://api.github.com/repos/oluwasolaonigbinde/mobility/commits/637841d95493bcc24334356da42097fa53a5d16f/check-runs). Focused execution produced **251 passed, 2 failed**; the pilot-gate suite alone produced 15 passed, 2 failed. Both failures are test/authority drift around newly `PRESENT` inputs and the now-`BLOCKED` W4-03B row ([failing test cases](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/tests/test_pilot_gate_evaluator.py#L148-L219)). |
| P1 | **CI omits release-critical root files.** | Path filters include the production Compose and Caddyfile but omit the root `Dockerfile`, `production.env.example`, and `requirements-production.*`; feature-branch pushes also do not run CI unless represented by a pull request ([ci.yml lines 3–39](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/.github/workflows/ci.yml#L3-L39)). |
| P2 | **The basemap is not configurable through the production image pipeline.** | Frontend code reads `NEXT_PUBLIC_MAP_STYLE_URL` and otherwise uses a local schematic ([map config lines 1–40](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/src/lib/map/config.ts#L1-L40)), but the Dockerfile only declares build inputs for revision and Sentry ([frontend Dockerfile lines 8–17](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/Dockerfile#L8-L17)). Because `NEXT_PUBLIC_*` is build-time state, a basemap account cannot be added by runtime configuration. |
| P2 | **Staging/configuration artifacts have drifted.** | `staging.env.example` says it can render production Compose but lacks required release IDs, image digests, origin, storage, cookie and backup settings ([staging example lines 1–31](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/staging.env.example#L1-L31)). The canonical production example omits several optional-but-live-critical email, scanner, legal/method and evidence settings even though Compose accepts them. |
| P2 | **Canonical architecture contains migration drift.** | Architecture still claims 24 migrations ending at `0024` ([architecture lines 529–545](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/architecture.md#L529-L545)); the exact revision contains a linear `0071` head ([0071 migration lines 1–17](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/alembic/versions/0071_report_issuances.py#L1-L17)). |
| P2 | **Security/PII hardening is incomplete.** | Backend scrubbing covers secrets, KYC, bank and coordinates but not common PII keys such as email, phone, person name or postal address ([observability.py lines 11–29](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/core/observability.py#L11-L29)). Caddy sets HSTS, nosniff and referrer policy but lacks CSP, anti-framing and Permissions-Policy ([Caddyfile lines 17–22](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/Caddyfile#L17-L22)). |

A further topology inconsistency should be resolved before choosing a managed database: architecture says an approved environment may map to managed PostGIS, but release validation requires database hostname `db` and Redis hostname `redis` ([release_contract.py lines 252–271](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/release_contract.py#L252-L271)).

## Controls that are already sound

- No embedded production credentials were found in the exact revision. Matches were local/demo/test/example values.
- Backend images copy only application, Alembic and locked production requirements; frontend build context excludes `.env*`.
- Production preflight enforces HTTPS origin, exact hostname, BFF-only CORS `[]`, non-placeholder secrets, immutable image digests, secure `__Host-` cookie naming and disabled trusted-proxy/test switches ([release validation](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/release_contract.py#L177-L250)).
- The session cookie is HTTP-only, secure in production, SameSite=Lax and path `/` ([cookie-options.ts](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/src/lib/auth/cookie-options.ts#L1-L8)).
- Fake payment/disbursement/ad-platform adapters are test-only and are not selected by normal production construction. Synthetic privacy mode and demo seeding are rejected by release preflight.
- API, worker and migration use the same backend image, materially reducing API/worker version skew.
- Revision provenance is strong: exact checkout, immutable image labels, rendered Compose/Caddy digest and ordered release state are verified ([release preflight lines 737–768](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/release_contract.py#L737-L768)).
- The focused release/configuration/health/preparation set passed **236 tests**, and all release shell files passed syntax validation.

## Configuration checklist

Before infrastructure startup:

- [ ] `ENVIRONMENT=production`; exact 40-character `RELEASE_REVISION`; unique release ID.
- [ ] Backend, frontend, PostGIS, Redis and Caddy references are immutable digests with matching revision labels.
- [ ] Approved domain, HTTPS origin, DNS and TLS; `BACKEND_CORS_ORIGINS=[]`.
- [ ] `SESSION_COOKIE_NAME=__Host-cardvert_session`; demo and synthetic flags false.
- [ ] Strong Postgres, Redis, JWT and backup secrets held outside Git in mode-restricted files or an approved secret store.
- [ ] Decide explicitly between the supported bundled PostGIS/Redis topology and a remediated managed-service topology.
- [ ] Distinct staging and production domains, databases, Redis instances, buckets, KMS namespaces, provider sandboxes and credentials.

Before protected data:

- [ ] Private, versioned object bucket with anonymous access denied.
- [ ] Mandatory malware scanner configured and included in readiness.
- [ ] Production KMS/vault implementation, custodian, rotation and rewrap procedure.
- [ ] Approved KYC, GPS, evidence, upload, retention, DSR and privacy references.
- [ ] Sentry/error reporting configured with staging and live separated; PII scrub tests expanded.
- [ ] Queue depth, worker heartbeat, scanner backlog, storage failures and partition coverage alerts.

Before money/commercial use:

- [ ] Concrete payment and disbursement adapters with sandbox webhook verification and polling.
- [ ] Settlement bank, issuer facts, commercial values, budget scope and approved budget thresholds.
- [ ] Maker/checker/reconciler roles and provider-finality runbook.
- [ ] Email provider/sender and receipt integration; phone operator and approved message copy.

Before maps/reporting/activation:

- [ ] Approved basemap licence and build-time configuration.
- [ ] Approved report/ROI methodology and legal/privacy authority.
- [ ] Concrete aggregate ad-platform adapter, account and activation budget.
- [ ] Live flags remain false until the corresponding gate evidence is committed to the protected operating record.

## Recovery and rollback gaps

The backup implementation itself is thoughtful: it quiesces writers, captures PostGIS and versioned objects, authenticates the manifest, encrypts the bundle and creates atomic completion markers ([backup_release.sh lines 75–178](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/backup_release.sh#L75-L178)). Restore verification uses an isolated database/object prefix and validates digests, PostGIS and migration identity ([verify_restore.sh lines 55–138](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/verify_restore.sh#L55-L138)).

Outstanding gaps:

- No approved backup scope, cadence, owner, retention source, RPO, RTO or restore evidence. Every field is deliberately a placeholder ([backup schedule](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/handover/backup-schedule.md#L1-L46)).
- No off-host scheduling or protected destination is implemented.
- No approved external restore or production recovery has been performed.
- Rollback keeps the forward schema and therefore depends completely on old-image compatibility; many migrations deliberately reject destructive downgrade once authoritative data exists, including `0071` ([downgrade guard](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/alembic/versions/0071_report_issuances.py#L243-L255)).
- Previous-image compatibility evidence is not mechanically produced.
- First-release smoke may pass by proving that the user table is empty, without exercising an authenticated product workflow ([release_smoke.sh lines 201–208](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/scripts/release_smoke.sh#L201-L208)).
- Destructive restore/traffic switching is appropriately not automated, but its owner and authorization process are unassigned.

## External actions in dependency order

1. Assign receiving operations, release, security, privacy, incident, money and evidence-checker roles.
2. Approve staging spend/account/domain and a distinct production account/domain.
3. Approve legal/privacy, retention/DSR, evidence/upload policies, report methodology and Abuja permits.
4. Supply company issuer facts, commercial values, campaign-budget scope, settlement bank and approved budget policy.
5. Select providers and obtain sandbox specifications for payment, disbursement, storage, scanner, KMS, email, phone, basemap and aggregate ad platform.
6. Implement and review the missing provider/KMS adapters against those specifications.
7. Create isolated staging infrastructure and protected secret custody.
8. Build and publish immutable exact-revision images; run full CI/security verification.
9. Configure provider sandboxes and execute signed webhook, idempotency, retry and reconciliation tests.
10. Establish off-host backup scheduling; perform isolated restore and previous-image recovery.
11. Run representative Android/iPhone install, permission, offline, route and four-hour battery exercises.
12. Re-run the six pilot gates. Current exact states remain blocked across money, GPS, commercial, advertiser, module-G and pilot ([canonical blocker register](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/progress.md#L2485-L2535)).
13. Conduct role-based training, then a monitored controlled pilot, then handover.

## Minimum production-like staging admission criteria

Admission requires all of the following:

- A remediated exact SHA with required GitHub checks green and no failing tests.
- Distinct staging accounts, data, secrets, providers and domain; no production PII or settlement credentials.
- Immutable same-revision API/worker/frontend images and a recorded rendered-config digest.
- Database at the single migration head with PostGIS; authenticated Redis; healthy same-revision worker.
- Private storage write/read/delete canary, mandatory scanner canary and production-equivalent KMS sandbox.
- Readiness fails on missing/wrong schema, Redis, worker or required storage/scanner state.
- Payment, disbursement and ad-platform sandbox adapters are concrete; disabled/fake adapters are rejected when staging-live gates are enabled.
- Off-host encrypted backup, isolated restore and mechanically generated previous-image compatibility evidence pass.
- Sentry/log collection and money/privacy/provider/queue alerts are operational with scrubbed evidence.
- Authenticated smoke exercises a real staging account and at least one bounded end-to-end workflow.
- Physical-device and route/battery evidence passes before any real-driver GPS collection.
- Named owner sign-off records that staging evidence is not production approval.

## Smallest repository remediation

1. Add provider factories/settings and concrete payment, disbursement, ad-platform and KMS custody implementations. Reject disabled or synthetic adapters whenever a corresponding live/staging gate is enabled.
2. Replace `/ready` with migration/PostGIS/Redis/worker checks, add required storage/scanner readiness, and make edge admission depend on the complete result.
3. Change login Redis failure to fail closed for new credential attempts.
4. Replace hand-authored rollback booleans with an executable previous-image readiness and report-schema canary whose signed/hash-bound result is consumed by release and recovery.
5. Add `NEXT_PUBLIC_MAP_STYLE_URL` to the frontend build contract and provenance; consolidate complete staging/production environment templates.
6. Fix the two pilot-gate tests and expand CI triggers to all release-critical Docker, environment and dependency files; require checks on the release branch/SHA.
7. Add CSP, anti-framing and Permissions-Policy headers; expand backend PII scrubbing for email, phone, names, addresses and unkeyed URLs.
8. Correct migration and staging documentation drift, then rerun the full release suite and independent recovery review.

Until those are complete, the safe decision is **do not admit Cardvert to production-like staging with real data or live providers, and do not schedule a pilot**.

