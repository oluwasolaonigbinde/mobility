---
source_surface: ChatGPT
project: TSS
conversation_id: 6a967dc0-eb14-83ea-a4b1-b4dde47dc0a7
displayed_title: Audit Authentication Authorization
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit Authentication Authorization

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict: **FIX**

The reviewed snapshot has a generally coherent authorization model and strong object-level tenant scoping, but it is not ready to pass an authentication red-team review. Four production-code defects materially weaken credential recovery, session invalidation, and brute-force resistance. A fifth verifier exception should be removed because it permits signed tokens that lack mandatory lifetime and revocation claims.

The most serious issue is a lost-update race between authenticated password change and password-reset completion. A holder of an existing authenticated session can race a victim’s reset, overwrite the newly reset password, and receive a replacement token at the same resulting `session_version`.

## Snapshot and review basis

* Repository resolved through the connected GitHub installation as `oluwasolaonigbinde/mobility`.
* Requested branch: `feat/pkg-04-build-first`.
* Requested commit: `637841d95493bcc24334356da42097fa53a5d16f`.
* The branch and commit compared as identical: zero commits ahead and zero behind.
* Commit timestamp: August 28, 2026 at 18:16:08 UTC.
* Commit parent: `90957252b22fb13f2d4877d29a88bc4473a4ee59`.

The environment could not resolve GitHub from the container’s Git client, so it could not materialize a normal Git checkout or run tests. I therefore inspected immutable, commit-addressed GitHub contents at the exact verified SHA. No source, branch, repository state, or external system was modified.

This is an execution-evidence limitation, not a reason to block source-level conclusions below.

# Threat model and trust boundaries

The relevant principals and boundaries are:

1. **Unauthenticated Internet client → Next.js BFF**

   * Login and recovery inputs originate here.
   * The BFF places the backend bearer token in an HTTP-only cookie.

2. **Browser → Next.js server actions and route handlers**

   * The browser does not directly read the access token.
   * Cross-origin protection relies on a host-only `SameSite=Lax` cookie and Next.js server-action origin enforcement.

3. **Next.js BFF → FastAPI backend**

   * The BFF converts the cookie into an `Authorization: Bearer` request.
   * The backend, not the frontend layout or middleware, is the authoritative authentication and authorization boundary.

4. **JWT verifier → live user record**

   * Role, status, forced-password state, and `session_version` are read from the database on protected requests.
   * JWT role claims are not trusted as authorization authority.

5. **Advertiser principal → active membership → active organization**

   * Advertiser object access is derived from current membership and organization state.
   * Campaign, creative, report, and stored-file identifiers must then be bound to that organization.

6. **Password-reset bearer → reset row → locked user row**

   * Reset tokens are capability-bearing secrets.
   * Database state controls expiry, one-time use, and `session_version` binding.

7. **Redis → login admission control**

   * Redis is the sole effective login throttling state store.
   * Its absence or failure currently converts the boundary into fail-open behavior.

8. **Notification worker and signing secret**

   * The reset outbox stores a reset-row identifier, not the raw reset bearer.
   * A trusted worker reconstructs the bearer using database state and the application secret.

# Confirmed findings

## 1. Password-change/reset race can defeat account recovery

**Severity:** High
**Confidence:** High
**Exploit prerequisites:** A valid authenticated session, knowledge of the current password, and the ability to race a victim’s password-reset completion. A copied browser bearer plus known password is sufficient.
**Impact:** An attacker can retain control after the victim successfully completes recovery. The reset token is consumed, the victim may see success, and the attacker can receive a replacement access token valid at the same resulting session version.

### Evidence

The authenticated change-password flow:

* operates on the already loaded current-user ORM object;
* verifies the old password;
* writes the new password;
* performs a Python-side `session_version += 1`;
* commits and issues a replacement token;
* does not lock or re-read the user row immediately before the credential update.

See:

* `app/api/v1/auth.py:467-519`

The recovery completion flow is more defensive: it locks both the reset row and user row, checks the token’s captured session version, writes the password, increments the version, consumes the reset token, and commits:

* `app/services/account_recovery.py:216-298`

That locking protects reset against a second reset operation, but it does not protect against a password-change transaction that read the user before the reset acquired its lock.

### Reproduction path

Assume the user begins with password `P0` and `session_version = 1`.

1. T1 calls authenticated change-password with `P0`.
2. T1’s dependency loads the user at version 1 and the route verifies `P0`.
3. Pause T1 before its flush/commit.
4. T2 completes a valid password reset.
5. T2 locks the reset and user rows, validates reset version 1, writes password `PV`, increments the row to version 2, consumes the token, and commits.
6. Resume T1.
7. T1 still holds a stale ORM object whose dirty values include its password, forced-change flag, and version computed as `1 + 1`.
8. T1’s update can overwrite the victim’s password with `PA` while writing `session_version = 2`.
9. T1 returns a replacement token carrying version 2.

The victim’s reset has therefore not invalidated the attacker’s transaction or resulting session.

### Smallest safe remediation

Move change-password into one credential-transition transaction that:

1. re-selects the user row with `SELECT ... FOR UPDATE`;
2. verifies the current password only after obtaining the lock;
3. verifies that the current database session version still matches the authenticated token;
4. writes the new password;
5. increments the session version from the locked row;
6. commits before minting the replacement token.

All credential-changing operations should use the same locked service primitive. An atomic database increment alone is insufficient if password verification was performed against stale state.

---

## 2. A reset issued before suspension or disablement remains usable

**Severity:** Medium; High where suspension is used for incident containment
**Confidence:** High
**Exploit prerequisites:** Possession of a valid reset bearer issued while the account was eligible.
**Impact:** A suspended or disabled account’s credential can still be replaced. Although current backend requests remain blocked while the status stays disabled, the token holder owns the credential if the account is later restored. This weakens suspension as an incident-response boundary.

### Evidence

Issuance eligibility allows only advertiser/admin users in active or invited status:

* `app/services/account_recovery.py:119-154`

Completion locks the user and checks:

* reset use;
* expiry;
* digest;
* captured `session_version`;
* role eligibility.

It does **not** recheck the user’s current status under that lock:

* `app/services/account_recovery.py:216-298`

Administrative status changes are generic field updates and do not increment `session_version` or invalidate outstanding reset rows:

* `app/schemas/users.py:47-53`
* `app/api/v1/admin.py:181-224`
* `app/services/users.py:133-158`

### Reproduction path

1. An active advertiser requests a password-reset link.
2. The administrator suspends or disables the user.
3. The reset holder submits the still-unexpired bearer.
4. The completion transaction finds the same session version and eligible role.
5. It changes the password and consumes the reset despite current suspension/disablement.

### Smallest safe remediation

Inside the already locked completion transaction:

* require the user to remain in an explicitly eligible status;
* reject suspended and disabled users with the same generic invalid-token response;
* keep the token unconsumed or consume it according to a deliberate policy.

In addition, every containment transition—at least suspend, disable, and security-sensitive role changes—should increment `session_version` and invalidate outstanding unused reset capabilities transactionally.

---

## 3. Login throttling can be silently absent and fails open during Redis faults

**Severity:** High for an Internet-facing login endpoint
**Confidence:** High
**Exploit prerequisites:** Redis is omitted, unavailable, timing out, returning an unexpected response, or failing script execution.
**Impact:** Unlimited credential stuffing and online password guessing, constrained only by infrastructure capacity or an undocumented external edge control.

### Evidence

The configured Redis URL is optional:

* `app/core/config.py:51-55`

If it is missing, the builder installs a no-op limiter:

* `app/core/rate_limit.py:264-284`

The no-op implementation always allows login:

* `app/core/rate_limit.py:60-71`

The Redis implementation broadly catches backend and script errors and deliberately returns an allowed decision:

* `app/core/rate_limit.py:214-250`

The intended limits—account, IP, and global—therefore exist only while Redis is configured and healthy.

### Reproduction path

Configuration case:

1. Start production without `REDIS_URL`.
2. Submit more than the nominal account limit of invalid logins.
3. The no-op limiter continues admitting requests.

Fault case:

1. Run with Redis configured.
2. Make Redis unavailable or force command/script failure.
3. Submit repeated invalid logins.
4. The exception path returns `allowed=True`.

### Smallest safe remediation

* Require a durable rate-limit backend in non-local/non-test environments during configuration validation.
* On limiter uncertainty, return a bounded `503 Service Unavailable` or otherwise fail closed instead of treating the request as allowed.
* Add monitoring for limiter readiness, failure decisions, and bypass activation.
* An ingress or WAF limit is useful defense in depth, but it should not be the unverified prerequisite that makes the application control real.

---

## 4. Logout does not revoke the bearer, and an in-flight refresh can restore the cookie

**Severity:** Medium
**Confidence:** High for bearer reuse; Medium-high for cookie resurrection because it depends on request timing
**Exploit prerequisites:** A copied access token, or an already-started refresh/keepalive request racing logout.
**Impact:** Access persists after the user believes they logged out. A copied token remains usable until expiry and can be refreshed before the absolute cap. A pending browser refresh can write a new cookie after logout clears it.

### Evidence

Frontend sign-out only deletes the cookie:

* `frontend/src/lib/auth/actions.ts:6-10`

There is no backend logout/revocation endpoint in the reviewed authentication router.

Refresh validates the existing bearer and issues a replacement token without consuming or revoking the old token:

* `app/api/v1/auth.py:521-571`

The proxy and driver session code can refresh a near-expiry session and write the replacement cookie:

* `frontend/src/proxy.ts:74-138`
* `frontend/src/lib/auth/driver-session.ts:47-112`
* `frontend/src/app/driver/keepalive/route.ts:8-31`

### Reproduction path A: copied token

1. Copy a user’s current bearer token.
2. The user logs out through the UI.
3. The UI deletes only its local cookie.
4. Use the copied bearer directly against a protected backend endpoint.
5. It remains valid until its normal expiry, assuming no other revocation event.
6. Before expiry, call refresh to obtain another token, subject to the 12-hour absolute cap.

### Reproduction path B: logout/refresh race

1. Start a keepalive or proxy refresh request.
2. Before it returns, invoke sign-out and clear the cookie.
3. The already authorized refresh returns a valid replacement token.
4. Its response subsequently sets the authentication cookie again.

### Smallest safe remediation

Introduce explicit server-side logout semantics.

The most precise option is a per-session identifier and revocation record so logging out one browser does not terminate all devices. A smaller but coarser option is to increment the user’s global `session_version` on logout.

The BFF should call that backend operation before deleting its cookie. To close the response-order race, associate cookie writes with a server-side session generation or session ID that has not been revoked rather than allowing any earlier refresh response to recreate the session.

---

## 5. JWT verification accepts missing expiry, absolute-age, and revocation claims

**Severity:** Low to Medium as a current exploit; Medium as a verifier design defect
**Confidence:** High regarding behavior
**Exploit prerequisites:** A legitimately signed legacy or alternate-issuer token lacking one or more claims, or compromise/misuse of the signing path. The current issuer and its immediate predecessor include the claims, so ordinary users cannot create such a token themselves.
**Impact:** Depending on the missing claim, a signed token can avoid expiry enforcement, the 12-hour absolute cap, or `session_version` revocation.

### Evidence

The issuer creates `sub`, `iat`, `auth_time`, `sv`, and `exp`:

* `app/core/security.py:26-52`

The decoder verifies signature and algorithm but does not require those claims:

* `app/core/security.py:54-66`

The request dependency checks `sv` only when it is present:

* `app/api/v1/dependencies.py:70-82`

It applies the absolute session cap only when `auth_time` is a numeric value:

* `app/api/v1/dependencies.py:84-96`

Consequences:

* no `sv` → session-version invalidation is skipped;
* no or malformed `auth_time` → absolute-age invalidation is skipped;
* no `exp` → the decoder has no expiration value to enforce.

Architecture text describes the `sv` exception as temporary legacy compatibility, but production code is authoritative and the exception remains active.

### Reproduction path

This is not reproducible through the current public issuer alone because it emits all claims.

Given any still-trusted signed token from a legacy or alternate issuance path:

1. Omit `sv` to avoid version comparison.
2. Omit or malform `auth_time` to avoid the 12-hour cap.
3. Omit `exp` to avoid ordinary expiry validation.
4. Present the token to a protected endpoint.
5. The request can proceed if `sub` resolves to a live eligible user.

### Smallest safe remediation

Configure decoding to require at least:

* `sub`
* `iat`
* `exp`
* `auth_time`
* `sv`

Then reject missing, boolean, non-integer, or out-of-range numeric claims. Remove the legacy `sv` exception after a bounded migration window; with a normal access-token lifetime of 60 minutes, that window should not be indefinite.

# Probe-by-probe result

| Probe                                                          | Result                                                                                                                                                                                                |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Session fixation, reuse, expiry, rotation, forced invalidation | **FIX.** Strong version validation for current tokens, but logout is local-only; refresh is replayable rather than one-time; verifier permits missing claims.                                         |
| Reset generation, replay, expiry, enumeration                  | **Mostly pass.** Strong random/signed bearer, digest at rest, one-time row, expiry, row locks, generic responses, and database-backed throttling. Status-transition defect remains.                   |
| Forced-password-change enforcement                             | **Pass.** Enforced centrally in backend dependencies, not merely by layouts.                                                                                                                          |
| CSRF and cross-origin mutation protection                      | **No confirmed code exploit.** Backend uses bearer authentication; BFF uses an HTTP-only, host-only `SameSite=Lax` cookie. Framework/deployment origin handling remains an external gate.             |
| Admin/advertiser/driver role confusion                         | **Pass with owner decision.** Backend uses the live database role. Existing tokens immediately inherit a promotion; deciding whether elevation requires reauthentication is a security policy choice. |
| Advertiser-organization isolation                              | **Pass for reviewed paths.** Active membership and active organization are re-derived on each request and object queries are organization-bound.                                                      |
| Removed, inactive, stale memberships                           | **Pass.** Invited/disabled memberships and suspended/disabled organizations do not satisfy the active-tenant resolver.                                                                                |
| IDOR through UUID paths                                        | **Pass for reviewed campaign, creative, reporting, file and driver-bound patterns.** Foreign and absent objects collapse to tenant-scoped 404s.                                                       |
| Frontend-only guards missing backend enforcement               | **Pass.** Frontend guards are subordinate to `/api/v1/me`; backend dependencies enforce status, role and forced-password state.                                                                       |
| Credential/reset-token/identity leakage                        | **Pass.** Passwords and bearer tokens are not written to audit/outbox records; reset email and IP values are HMACed for rate-limit accounting.                                                        |
| Login and recovery rate-limit gaps                             | **FIX.** Recovery limits are durable and existence-neutral; login limits can disappear or fail open.                                                                                                  |
| 401/403/404 tenant leakage                                     | **Pass.** Foreign/absent tenant resources generally return 404; wrong role returns 403; invalid authentication returns 401.                                                                           |
| Reset, revocation and membership races                         | **FIX.** Confirmed reset/change-password lost-update race and reset-versus-suspension lifecycle gap.                                                                                                  |

# Controls that correctly fail closed

## Live database authorization

Protected requests resolve the bearer’s subject to the current user record and then enforce:

* account status;
* role;
* forced-password state;
* session version when the claim is present.

The role is not accepted from a JWT or browser-provided field:

* `app/api/v1/dependencies.py:37-132`

This means suspension, disablement, and role demotion take effect on the next protected request even when an older token remains cryptographically valid.

## Forced-password-change boundary

When `must_change_password` is set, the backend allows only the narrow recovery set:

* `/api/v1/me`
* `/api/v1/auth/change-password`
* `/api/v1/auth/refresh`

All other protected routes fail with 403:

* `app/api/v1/dependencies.py:98-118`

The password-change operation advances `session_version`, and the frontend installs the returned replacement token:

* `app/api/v1/auth.py:467-519`
* `frontend/src/lib/auth/change-password-action.ts:38-85`

The concurrency defect does not negate this central enforcement; it affects transaction serialization.

## Recovery secrecy and replay resistance

Recovery has several good controls:

* normalized account and IP values are HMACed before storage;
* nonexistent accounts still consume the same account/IP limiter path;
* account and IP buckets are transactionally serialized;
* only eligible roles and statuses result in token issuance;
* the database stores a token digest, not the bearer;
* expiry and one-time use are checked under row locks;
* the token binds user, reset row, captured session version and expiry;
* successful completion advances session version.

Relevant implementation:

* `app/services/account_recovery.py:48-214`
* `app/services/account_recovery.py:216-325`
* `app/models/contact.py:45-127`

## No reset bearer in the outbox

The password-reset notification outbox carries the reset-row UUID rather than the raw bearer:

* `app/services/notifications.py:218-246`

The trusted worker reconstructs and verifies the delivery token from the reset row and application secret:

* `app/services/account_recovery.py:301-325`
* `app/services/notifications.py:566-647`

This avoids turning the durable outbox payload into a bearer-token store.

## Tenant and object scoping

The active advertiser organization resolver requires both:

* an active membership; and
* an active organization.

It returns no organization for invited/disabled membership or suspended/disabled organization:

* `app/services/organizations.py:48-81`

Campaign operations bind supplied UUIDs to that derived organization:

* `app/services/campaigns.py:102-132`
* `app/services/campaigns.py:169-216`
* `app/services/campaigns.py:478-521`

Nested creative and file operations also bind the parent and organization rather than trusting the child UUID alone:

* `app/services/campaigns.py:534-601`
* `app/services/campaigns.py:717-798`
* `app/services/stored_files.py:145-226`
* `app/services/stored_files.py:508-631`

Advertiser reporting authorizes the campaign before querying dependent records:

* `app/api/v1/advertiser_reports.py:41-181`
* `app/services/reports.py:93-138`

The code generally returns the same 404 for nonexistent and foreign tenant objects, reducing existence leakage.

## Browser token handling

The BFF stores the token with:

* `HttpOnly`;
* `Secure` in production;
* `SameSite=Lax`;
* path `/`;
* no broad Domain attribute;
* lifetime bounded by the backend response.

See:

* `frontend/src/lib/auth/session.ts:8-48`
* `frontend/src/lib/auth/cookie-options.ts:1-16`

Unverified token decoding in the frontend is used for refresh timing, not as authorization authority:

* `frontend/src/lib/auth/token.ts:1-49`

# External gates versus code defects

## Code defects

These can and should be closed in the repository:

1. serialize change-password with password-reset and other credential transitions;
2. recheck status during reset completion and revoke reset/session state on containment transitions;
3. make production login throttling mandatory and fail closed;
4. implement backend logout/revocation and race-safe refresh semantics;
5. require all security-critical JWT claims.

## External or runtime gates

These cannot be proven from a source snapshot alone:

### Reverse-proxy origin integrity

Next.js server-action CSRF protection depends on correct `Origin`/`Host` behavior. The application does not define a custom `serverActions.allowedOrigins` list:

* `frontend/next.config.ts:1-8`

Deployment evidence should show that:

* the proxy preserves or safely rewrites `Host` and `Origin`;
* no untrusted client can inject the internal trusted-client-IP marker;
* all public traffic uses HTTPS;
* production cookies are actually emitted with `Secure`.

### Redis readiness

Even after changing the application to fail closed, production evidence should show:

* Redis is present;
* health is monitored;
* Lua scripts execute successfully;
* latency and error alerting exist;
* rate-limit keys expire as expected.

Under the reviewed code, this is partly an external gate but also a confirmed code defect because absence and failure are deliberately admitted.

### Secret and key management

Source review cannot establish:

* signing-secret entropy;
* access controls around the secret;
* rotation history;
* whether separate environments use separate values;
* whether logs or crash dumps expose environment configuration.

### Notification-provider behavior

The source does not persist reset bearer tokens, but runtime evidence should confirm that email-provider logs, observability payloads, tracing, dead-letter systems, and support tooling do not retain reset URLs longer than necessary.

### Focused tests

Tests could not be executed because the runtime could not create a Git checkout or install/use repository dependencies. Focused tests should be run in an authorized checkout for:

* concurrent change-password versus reset completion;
* reset completion after suspend/disable;
* login behavior with missing Redis and injected Redis failure;
* logout followed by copied-token use;
* logout racing keepalive/refresh;
* signed tokens individually missing `exp`, `auth_time`, or `sv`;
* foreign campaign/creative/file/report UUID equivalence to absent UUIDs.

# Owner decisions

These are not release-blocking defects by themselves, but the policy should be explicit.

## Privilege elevation and existing sessions

Because roles are read live from the database, changing an advertiser or driver to admin immediately upgrades every still-valid bearer for that user. This is internally consistent and makes demotion immediate, but it means an old stolen token also gains the new privilege.

A higher-assurance policy would:

* advance `session_version` on role changes;
* require fresh authentication before privileged elevation becomes usable;
* optionally require MFA for administrator elevation.

## Multiple active advertiser memberships

The data model permits more than one active membership for the same advertiser, while the service deterministically selects the newest active membership:

* `app/models/organization.py:61-112`
* `app/services/organizations.py:48-81`

That behavior avoids nondeterministic access, but it silently chooses a tenant rather than requiring an explicit tenant selection.

The owner should choose one model:

* exactly one active advertiser organization, enforced by a database invariant; or
* multiple organizations, represented explicitly in the session/request and reauthorized on every object access.

The current behavior did not produce a confirmed cross-tenant IDOR because objects are bound to the selected organization.

# Remediation order

1. **Lock and serialize all credential transitions.** This closes the high-severity recovery race.
2. **Tie suspension, disablement, and security-sensitive role changes to session/reset invalidation.**
3. **Require functioning production login throttling and fail closed on limiter errors.**
4. **Add backend session revocation and make refresh/logout ordering race-safe.**
5. **Make JWT security claims mandatory and remove the legacy missing-`sv` path.**
6. **Document and test the privilege-elevation and multi-membership policy.**
7. **Collect runtime evidence for proxy-origin integrity, Redis readiness, secret handling, and provider-log redaction.**

The system’s role checks, forced-password boundary, recovery secrecy, tenant lookup, and UUID scoping are substantially fail-closed. The verdict remains **FIX** because the credential race, stale reset capability, optional login throttling, and local-only logout affect core account-security guarantees rather than peripheral hardening.
