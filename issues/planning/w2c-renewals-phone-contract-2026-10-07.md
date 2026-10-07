# Wave 2 C — renewal and reverse phone verification contract

Owner authority: `Cardvert_W2C_Renewals_Phone_Brief_2026-10-07.md`;
REQ-119/120, D66/67, architecture v1.124. Work only in `mobility-w2c`,
branch `w2/renewals-phone`, base `ec267529`. No push, CI, deployment, provider
calls, account-access or tmp reads. No launch-queue changes. Local commit is
authorized by the brief; merge and Claude acceptance remain owner actions.

## Outcome and bounded plan

1. Add authenticated document status and person/bank renewal capture in the
   onboarding/KYC domains. Reuse encrypted bank/NIN capture, scanned owned
   files, immutable revisions, exact retry identity and existing review reads.
   Reuse vehicle submission and extend their rejection/expiry guards. Lock
   existing work-eligibility authority before profile/submission mutations.
   Account status, rather than derived work eligibility, governs portal access.
   Staff decisions carry the displayed submission ID for every decision,
   including rejection/expiry, and exact decision retries retain that identity.
   Use ordered User locks before Application, profile and revision locks across
   capture, review and affected account-setup operations; refresh and revalidate
   authority after locking. Standalone KYC cannot bypass combined renewal capture.
2. Profile offers a renewal form only for rejected/expired current submissions;
   show current submitted document names, rejection reason, recorded vehicle
   approval expiry and waiting state. Reuse signed-in private upload BFFs and
   scan polling. Identity/bank resubmission captures a complete revision;
   vehicle renewals freeze the current owned vehicle without editing identity.
   Missing policies stay unset; never infer a licence expiry from a vehicle
   approval date. Handle missing documents separately from renewal eligibility.
3. Staff Documents displays current person/bank and each current vehicle
   revision. Use existing audited View/NIN/bank controls and decision services,
   including profiles with no public application. Approval rechecks current
   revision and scan/bank authority, without reactivating suspended profiles.
4. Replace operator-send/driver-enter verification APIs and callers. Driver
   request response alone includes the code and configured Terrax destination,
   with no-store caching. Staff read models explicitly exclude the code and
   hash. Staff records code plus sender against the driver profile/current
   challenge. Serialize profile/user → phone → challenge; invalid codes and
   sender mismatches consume durable attempts. Expiry, exhaustion, changed
   phone, inactive account, foreign challenge and replay are denied. Use existing
   keyed code hashing, request windows and attempt limits.
   Count requests across all phone versions for the driver; concurrent requests
   serialize. Return the same live challenge after reload/lost response;
   replace only terminal/expired challenges subject to the account-wide limit.
   Clear displayed codes after phone changes and on expiry; exhausted/expired
   states explain how to request another code. Staff input errors never echo
   code or sender, including malformed-field validation errors.
5. Configured destination enables synthetic local demonstration only in
   development/preview; production/staging require approved consent wording
   and named operator authority. Production/staging templates stay blank.
   Keep purpose-specific WhatsApp consent and contact-task gates intact.
   Driver Profile contains phone editing/status and Verify my phone. Staff
   driver Phone and Support → Driver contact use Record phone verification.
6. Register reserved unroutable fictional numbers and document seed renewal
   examples; no outbound messaging. Update records, API baselines together,
   migration 0100 if contact persistence changes (parent 0099), and operational
   guidance. No changes to other lane domains, dependencies or baselines.

Affected files: `app/{services,schemas,api/v1}/contacts.py`,
`app/{services,schemas}/driver_onboarding.py`, KYC and vehicle services/routes,
contact model/migration as needed, driver profile renewal/phone components and
BFF/actions, admin driver hub and its existing review/actions, Support contact
surface, `app/seeds/demo.py`, `docs/demo-data.md`, required decision/architecture
records and the three generated API baselines. Relevant touched tests only.

No new expiry policy, live legal wording, provider send, money calculation,
notification redesign, campaign UI, production enablement or compatibility
layer. Lane 1 G1 was searched in current docs/issues and its integration commit;
current source has rejection/expiry resubmission checks but public application
capability access terminates on approval. Reuse that design without restoring
public access to active drivers.

## Acceptance and verification

| ID | Criterion | Required evidence |
|---|---|---|
| C1 | Active signed-in accounts renew rejected/expired identity/bank and owned vehicle documents; unrelated/approved/pending revisions cannot be replaced; exact retries converge | Failing reproduction then scoped API/service tests; PostgreSQL different-request, exact-request and review-versus-renewal races: one new revision, no orphan bank capture, stale decisions denied |
| C2 | Protected/scanned files and encrypted capture retained; review of current revisions uses D58 audited View and bank/NIN checks; invalid work remains blocked | Scan/RBAC/stale/audit tests and integrated review simulation |
| C3 | Driver sees actionable reason, real recorded dates, submitted names and waiting state, with loading/error/retry handling | Component tests and desktop/375px browser walkthrough/screenshots |
| C4 | Code appears only in authenticated driver response/screen; hash only in storage; staff record checks current saved phone and single-use expiry | API tests comparing staff reads, mutation successes, malformed-input/forbidden/expired/exhausted errors, BFF/action responses and audit/log/storage content against the actual issued code; browser driver/staff screenshots |
| C5 | Durable bounded attempts, account-wide request limit across phone changes, replay/expiry/phone replacement/unauthorized and concurrent completion denial | Deterministic negatives and real PostgreSQL races; browser reload/lost-response recovery, expiry/exhaustion, phone-change stale-code clearing and success |
| C6 | Missing Terrax config hides button and denies server issuance; live operator/wording gates preserved; contact completion still requires consent | Config/API/component tests and contact task simulation |
| C7 | Reserved demo numbers realistic/unroutable, development/preview only; records and generated contracts consistent | Seed idempotence/touched seed tests, environment checks, schema generation and R14-B fixtures |
| C8 | Touched tests/static checks pass, changed lines ≥90%, branches ≥80%; required independent reviews PASS | Scoped coverage calculation against base; plan review, privacy/security specialists, same post-build reviewer reassesses FIX until PASS |

Checkpoints: reviewed contract → implementation/reproductions → integrated
criterion evidence → privacy/security reviews → consolidated minimal-change
PASS → one local commit. Keep requests IN PROGRESS until owner merges after
combined CI; no receipt claims master acceptance or live readiness.
