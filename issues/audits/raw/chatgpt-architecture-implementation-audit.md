---
source_surface: ChatGPT
project: TSS
conversation_id: 6a967da0-6524-83e9-ad55-5c49240a857f
displayed_title: Audit architecture implementation
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit architecture implementation

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict: **FIX**

The immutable gate passed. GitHub resolved commit `637841d95493bcc24334356da42097fa53a5d16f`, and `feat/pkg-04-build-first` points to that exact commit. All cited source was read at that SHA.

The principal runtime shape is coherent, and I found no evidence that missing live providers, legal approvals, deployment, or pilot inputs are being bypassed. The integrated system is nevertheless not fully truthful to its declared architecture: there are eight material control, authority, and boundary violations.

## Compact architecture map

```text
Delivery control
docs/progress.md ──► scripts/validate_progress.py ──► package/controller state

Runtime
Browser
  └─► Next.js server/BFF
        └─► FastAPI /api/v1 routers
              └─► domain services
                    └─► PostgreSQL / models

Async
arq worker ──► jobs ──► services ──► provider adapters

Contract
FastAPI schema ──► openapi.json ──► generated TypeScript + docs snapshot
```

The Next.js API client and environment access are server-only, FastAPI has one assembled router tree, and arq has one worker registry. The material deviations are: authentication policy in the HTTP router, email policy in a job, the ad-platform port inside a service, and administrative authority duplicated across services.

## Confirmed findings

### 1. HIGH — `Controller state: COMPLETE` silently means build exhaustion, not declared completion

**Violated authority.** `AGENTS.md` and the execution lock reserve `COMPLETE` for the point after PKG-09 closes, with every package-owned checklist item `DONE`. With no runnable work and remaining external blocks, the declared state is `PAUSED — EXT-ID`. `docs/progress.md` repeats that `COMPLETE` is valid only after all nine packages and all 71 items are `DONE`. `AGENTS.md:79-98,138-151`; `docs/progress.md:26-50`.

**Exact evidence.** The same progress file instead declares `COMPLETE` while PKG-03, PKG-08, and PKG-09 remain `BLOCKED`; W2-01C and checklist items 67–71 are explicitly not `DONE`. `docs/progress.md:59-78,1568-1571`. The validator was amended to accept a second meaning, `build_exhausted`, where packages and items may remain blocked. `scripts/validate_progress.py:793-817`.

D23 allows build packages to close without fabricating unavailable real-world evidence, but it also requires that evidence to remain explicitly incomplete and keeps release/pilot gates fail-closed. It does not authorize changing the controller grammar while packages and checklist items remain `BLOCKED`. `docs/decisions-log.md:47`.

**Reachable failure.** Delivery automation, handover readers, or an owner can treat `COMPLETE` as scope completion even though deployment, controlled-pilot, training, acceptance, and handover obligations remain unfinished. Runtime gates may still deny live actions, but the sole operational control document now misstates programme state.

**Affected packages.** All packages; directly PKG-03, PKG-08, PKG-09, W2-01C, and W4-03A through W4-04B.

**Smallest correction.** Restore the current controller to an explicit registered pause, such as `PAUSED — EXT-RELEASE-ENV`, and remove `build_exhausted` as an accepted meaning of `COMPLETE`. The existing pointer text can continue to record that local/provider-neutral preparation is exhausted. A separately named `BUILD COMPLETE — EXTERNAL GATES` state would be a larger architecture amendment, not the minimum fix.

---

### 2. HIGH — Active-admin authority is duplicated with weaker locking and conflicting semantics

**Violated authority.** Administrative authorization is intended to be a transactional service-boundary authority. The canonical helper states that its `FOR UPDATE` lock prevents a concurrent disable from slipping between authorization and the protected operation. `app/services/admin_authorization.py:1-31`.

**Exact evidence.**

* `app/services/billing.py:193-203` defines another `_active_admin` using `session.get`, without a row lock, and emits a different code, `ADMIN_REQUIRED`.
* `app/services/campaign_assignments.py:40-45` imports that private billing helper, and `:434-446` invokes it as the authority for an assignment write.
* `app/services/heatmaps.py:234-248` defines another unlocked copy. The audience domain does likewise.
* Other services, including campaigns, already use the canonical helper, proving the split is not a deliberate uniform convention. `app/services/campaigns.py:25-28`.

**Reachable failure.** An admin can pass an unlocked duplicate check, be disabled concurrently, and still complete the privileged domain mutation. Different domains also return different public error codes for the same authority decision. Campaign assignment now depends on a private billing implementation for identity authorization, so a billing-local change can alter matching/assignment authority.

**Affected packages.** PKG-03 billing, PKG-05 audience/heatmaps, and PKG-06 matching/assignments.

**Smallest correction.** Make `require_active_admin` return the locked `User` when callers need it, then replace the billing, heatmap, audience, and other copies. Remove the private cross-domain import from `campaign_assignments.py`.

---

### 3. HIGH — The `[BUILT]` CI branch-coverage claim is false, and the exact controller-closing SHA has no checks

**Violated authority.** Architecture §10.3 claims the workflow’s push trigger covers every branch. P11 requires claims to be verifiable, and D23 requires exact CI to agree before build closure. `docs/architecture.md:750-763`; `docs/decisions-log.md:47`.

**Exact evidence.** `.github/workflows/ci.yml:3-25` limits push execution to `master`; pull requests can trigger CI, but this branch has no associated run at the audited SHA. GitHub reports zero check runs for `637841d`.

The exact commit changed the controller state, validator behavior, and validator tests. The absence of a check run does not prove those tests failed or were not run locally; it proves the repository has no exact-SHA GitHub CI evidence for the state it declares terminal.

**Reachable failure.** A direct push to the working branch can alter delivery control, source, migrations, or contracts without running backend, frontend, contract, build, or E2E gates. The final controller commit followed that path.

**Affected packages.** All packages, especially PKG-09/controller closure and every package relying on an “exact CI” evidence statement.

**Smallest correction.** Remove the `master`-only push restriction or add an explicit exact-SHA workflow-dispatch/PR requirement for closure commits. Record a successful run for the exact candidate before declaring terminal control state. If branch-only CI is intentionally unsupported, correct the `[BUILT]` architecture claim and the closure contract.

---

### 4. MEDIUM — The contract gate checks only `openapi.json → TypeScript`, not `FastAPI → openapi.json`

**Violated authority.** P3 and §9 require the backend contract, root OpenAPI file, generated TypeScript, and documentation snapshot to move together. `docs/architecture.md:690-719`.

**Exact evidence.**

* The frontend CI step regenerates `schema.d.ts` from the already committed `openapi.json` and diffs only the TypeScript file. `.github/workflows/ci.yml:99-111`.
* `tests/test_openapi.py:1-9` merely verifies that the runtime schema generates and contains three health paths; it does not compare the complete runtime schema with the committed artifact.
* `scripts/update_openapi_snapshot.py:1-13` can regenerate both JSON artifacts from `create_app().openapi()`, but CI does not run it and diff the result.
* `npm run api:sync` fetches the live backend schema, but CI uses `api:types`, not `api:sync`. `frontend/package.json:5-17`.

**Reachable failure.** A backend endpoint or schema can change while committed `openapi.json` remains unchanged. Backend tests can pass, the TypeScript drift check can also pass because it regenerates from the stale committed file, and the frontend and documentation remain consistently wrong together.

No current root-versus-document snapshot divergence was confirmed: both JSON artifacts are the same Git blob at this SHA. The defect is the missing backend-to-artifact enforcement edge.

**Affected packages.** Every backend/frontend package that changes an endpoint or schema.

**Smallest correction.** In backend CI, run `python scripts/update_openapi_snapshot.py`, fail on a diff to both JSON artifacts, and only then run TypeScript generation and its diff.

---

### 5. MEDIUM — The reachable email job owns notification, identity, and retry business rules

**Violated authority.** Architecture §14.3 says jobs contain no business logic and must only find work, call services, and record outcomes. §20 assigns notification policy to services and provider translation to `adapters/messaging`. `docs/architecture.md:943-953,1668-1738`.

**Exact evidence.** `app/jobs/email_delivery.py`:

* determines password-reset and onboarding recipient eligibility;
* queries advertiser organizations, memberships, organization state, and email preferences;
* validates reset/session-version/expiry authority;
* reconstructs password-reset and onboarding secrets;
* renders the template;
* owns claim leases, attempts, exponential backoff, and terminal notification transitions.

See `app/jobs/email_delivery.py:30-139,140-267`.

The path is production-reachable because `sweep_email_notifications` is registered in the arq cron list. `app/jobs/worker.py:19,126-133`.

The actual SMTP transport is correctly isolated in `app/adapters/messaging/email.py`; the violation is the domain state machine above it.

**Reachable failure.** Recipient and token validity are authoritative both when the business event creates an outbox row and again inside an arq-specific module. A request, CLI replay, or another worker cannot invoke the same service authority. Changes to membership, recovery, onboarding, or retry policy can update one path while leaving the other operationally different.

**Affected packages.** PKG-04 communications/account recovery and PKG-06 driver onboarding.

**Smallest correction.** Move claim, eligibility, runtime-payload construction, template selection, retry, and status transitions into a notification/email-delivery service. Leave the job to select IDs, call that service, and emit run telemetry. Keep SMTP and future providers in `adapters/messaging`.

---

### 6. MEDIUM — Authentication authority is split between a narrow service and the HTTP router

**Violated authority.** P4 requires reusable service-layer business logic, and §30 places any auth change in `core/security.py` and `services/auth.py`. `docs/architecture.md:197-210,2420-2423`.

**Exact evidence.** `app/services/auth.py:1-21` only looks up a user and verifies the password. It returns a suspended or disabled user when the password matches.

The HTTP router separately owns:

* rate-limit reservation and release;
* active-account policy;
* success/failure audit events;
* token issuance;
* password mutation and `session_version` rotation;
* absolute refresh lifetime and refresh auditing.

See `app/api/v1/auth.py:239-324,529-689`.

**Reachable failure.** The function named `authenticate_user` is not the reusable authentication authority promised by the architecture: a CLI, future worker, or internal caller receives a successfully authenticated suspended/disabled user unless it independently reproduces router policy. The current HTTP login compensates, so this is not evidence of a present disabled-user HTTP login bypass; it is a confirmed contradictory authority seam.

**Affected packages.** PKG-01 authentication, PKG-04 recovery, PKG-06 public onboarding, and PKG-07 session/BFF behavior.

**Smallest correction.** Introduce service commands for login, password change, and refresh that own account-state, rate-limit, audit, session-version, and token decisions. Keep request parsing, client-IP extraction, dependency injection, and HTTP envelope mapping in the router.

---

### 7. MEDIUM — The ad-platform port, implementations, and factory are inside the domain service

**Violated authority.** P5 and the dependency map put provider interfaces/implementations under adapters; §30 specifically assigns ad-platform activation to `adapters/ad_platforms/`. `docs/architecture.md:201-205,2385-2400,2442-2444`.

**Exact evidence.** `app/services/audience_delivery.py:42-96` defines:

* `AdPlatformAdapter`;
* the activation request/result types;
* disabled and fake implementations;
* the adapter factory.

The API composition dependency imports both the port and factory from that service. `app/api/v1/dependencies.py:22-35`.

**Reachable failure.** The synthetic activation path already composes through a provider boundary owned by the domain module. A later live implementation can therefore be added in the service without crossing a visible adapter boundary or dependency check.

The current impact is constrained: the factory always returns the disabled adapter, and no live ad-platform push is authorized while `EXT-AD-PLATFORM` is missing. No live audience disclosure was found.

**Affected packages.** PKG-05 audience export/activation.

**Smallest correction.** Move the protocol, request/result transport types, fake/disabled implementations, and factory to `app/adapters/ad_platforms/`; inject the port into the audience service.

---

### 8. LOW — The mandatory current-state and feature-placement maps were not amended after built packages

**Violated authority.** §1 requires architecture changes and implemented target items to update the architecture in the same change. P12 says a feature an agent cannot correctly place from the document is a document defect.

**Exact evidence.**

* §6 still claims 82 operations, only three `/auth/*` operations, “no register,” and that every business endpoint is role-prefixed except `/me` and future webhooks. `docs/architecture.md:290-326`.
* The reachable contract now includes public driver registration, status, capability-token file upload, and additional onboarding endpoints under `/api/v1/auth/*`. `app/api/v1/auth.py:321-420`.
* The mandatory §30 map still says data-subject requests are an “ops runbook (no code at pilot).” `docs/architecture.md:2449-2451`.
* A production router and service-backed DSR control plane are included at `/admin/privacy/dsr-requests`. `app/api/v1/privacy_dsr.py:1-127`; `app/api/v1/router.py:28-47`.

**Reachable failure.** The document used as the mandatory pre-flight map can cause a later agent or reviewer to create a second registration/DSR path, omit the public-applicant threat boundary, or wrongly conclude that existing DSR behavior is not reachable.

**Affected packages.** PKG-05 privacy/DSR and PKG-06 public application/onboarding.

**Smallest correction.** Refresh §3’s build statuses, §6’s current route inventory and exceptions, and §30’s DSR/onboarding code homes; append the required changelog row. No runtime redesign is needed.

## Rejected suspicions

* **No browser-to-FastAPI bypass was confirmed.** The shared frontend API client and environment modules are marked `server-only`, and the current-user helper treats backend `/me` as authority rather than a frontend role decision.
* **No current committed JSON-baseline divergence was found.** Root `openapi.json` and the documentation snapshot are the same blob. Finding 4 concerns the missing enforcement edge back to runtime FastAPI, not a fabricated present diff.
* **The legacy creative state is not current launch authority.** `READY` is explicitly retained as readable legacy state, while current architecture requires managed, reviewed creative evidence for offers and activation. `app/models/campaign.py:50-58`.
* **The raw-ping heatmap reader is not an accidental competing implementation.** It is explicitly grandfathered in §22.2 and is now subject to the disclosure gate and contributor floors.
* **No direct live provider call from a service was confirmed.** Email transport is in its adapter, ad-platform activation is disabled, and live provider gates remain closed. The reported ad-platform issue is placement of the port/factory, not evidence of a live push.
* **No dependency cycle was confirmed in the inspected entry-point and suspected service graph.** A repository-wide automated cycle scan was not available, so this is not a claim that every possible import cycle has been disproved.

## Honest external and live gates

The following remain genuine external/live gates and must not be inferred complete from the controller label:

* provider and custody inputs for payment, disbursement/settlement, storage, malware scanning, KMS, email, phone operations, basemaps, and ad-platform activation;
* legal/privacy and reporting-method approval;
* production release environment and staging approval;
* physical-device, route, battery, and live recovery evidence;
* Abuja pilot permits/facts, controlled-pilot evidence, operations-owner rehearsal, named acceptance, brand approval, and protected credential handover.

PKG-03, PKG-08, and PKG-09 remain blocked, and W4-03A through W4-04B explicitly say that `DONE` still requires live deployment, controlled-pilot, training, acceptance, and handover evidence. D23 leaves those gates fail-closed.

I did not run the full suite, install dependencies, deploy, or invoke providers. Terminal networking could not retrieve an immutable archive, so no repository-wide automated import-cycle scan or focused executable check was run. This limitation is not itself a code defect. All necessary requested documents and the source files supporting the findings were accessible through GitHub at the exact SHA, and no checkout or repository state was changed.

**No owner decision required.**
