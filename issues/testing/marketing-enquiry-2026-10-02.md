# REQ-070 — public marketing conversion

Owner approved the assessed fixes with “go ahead” on 2 October 2026.
Review-required under verified-feature-delivery: public input, email integration
and a new UI flow. Unrelated admin work remains outside this change.

## Contract

1. All advertiser acquisition buttons say **Request a campaign quote** and
   reach the on-page enquiry form; all driver action buttons say **Apply to
   drive** and reach `/apply`; existing-account links say **Sign in** and reach
   `/login`. Both audience actions are reachable from desktop and mobile headers.
2. The form collects company, contact name, reply email, optional phone and a
   campaign brief. Inputs are bounded and validated at the action and backend.
   Labels, pending, error, retry and success are accessible; failures preserve
   entered values. A visible email alternative remains available.
3. The server action relays through the typed BFF to a public backend endpoint.
   The service uses the existing email adapter and fixed official recipient.
   Success means SMTP acceptance, not confirmed inbox delivery. No account,
   campaign, database lead record, automatic reply or marketing subscription is
   created. Submitted text is escaped in HTML and never controls mail headers.
4. Runtime enablement defaults off. Streamed JSON is capped at 8 KiB before
   parsing, including requests without Content-Length. Redis IP/global limits are atomic, expire
   and fail closed. The existing trusted-edge IP boundary applies. Missing
   provider configuration and sending failures never report success. No form
   payload is logged or stored in Cardvert; contact details are used to answer
   the enquiry. No live provider call is authorized.
5. `/landing` and its current compatibility handling are removed. Update
   applicable decisions, current architecture, configuration and all three API
   baselines without changing the launch package queue or unrelated work.
6. Verify each criterion with focused tests, desktop/mobile landing browser
   checks and a synthetic browser-to-local-Mailpit flow. Rerun the native
   contract fixtures after the API baseline change. Obtain plan review, named
   security/privacy review and final minimal-change-review PASS.

## Plan and boundaries

Use the existing marketing design and React action-state pattern. Add one form,
one server action, one backend schema/router/service and a small Redis limiter.
Send synchronously with no background or automatic resend; transport timeout
can be uncertain, so no exactly-once guarantee is offered. Do not add CRM,
account signup, pricing, uploads, provider credentials, deployment or new
dependencies. No commit, push or merge has been authorized.

Checkpoints: independent plan review; bounded implementation; per-criterion
verification and security/privacy review; consolidated final review.

## Evidence

Request remains IN PROGRESS until owner-authorized commit, full branch CI and
merge. No commit, push, provider-account change or deployment was performed.

Plan review: independent `marketing_plan` reviewer recommended proceeding with
bounded pre-parse ingress, direct-bypass tests, mandatory real Redis evidence
and the separate security/privacy review. All findings accepted into this contract.

| Criterion | Local verdict | Evidence |
| --- | --- | --- |
| 1 — labels and destinations | PASS | Landing browser checks confirm distinct brand/driver paths and header login/application links; header action tests confirm the mobile menu closes on selection. Shared CTA constants eliminate varied labels. |
| 2 — accessible form states | PASS | Form/action unit cases cover labelled required fields, bounds, non-string entries, pending disablement, field-error association, error retention/retry and confirmed success. Desktop/mobile browser submissions complete without a mail client. |
| 3 — fixed-inbox transport | PASS | Both browser profiles submit through the real Next action and local FastAPI to Mailpit; the captured recipient is the official inbox. Backend tests prove fixed headers, HTML escaping, absence of response/log input echoes, and failure without false success. No DB dependency or user/campaign mutation exists in this path. |
| 4 — bounds and abuse controls | PASS | Focused backend tests include >8 KiB streamed input without Content-Length, nested JSON, invalid/extra fields, disabled flow, missing Redis, provider failure and untrusted IP headers. Real local Redis proves exactly two accepted concurrent reservations at IP limit two, cross-IP global refusal, positive TTL and expiry recovery. |
| 5 — removal and documentation | PASS | `/landing` now returns 404 in both browser profiles; obsolete theme handling removed. REQ-070/D52/Q29/current brand rule, §27/§30/changelog and local config updated; launch queue untouched. API JSON baselines compare semantically equal; generated client contains the new endpoint. |
| 6 — verification and review | PASS | Eight focused frontend files pass 151 cases, including tracker, queue, evidence and capability fixtures; final header recheck passes two cases after hydration correction. Backend suite passes 32 cases. Scoped marketing TypeScript, ESLint, formatting and Ruff pass. Dedicated security/privacy reviewer PASS after independently proving missing-Redis and deep-JSON regressions. Consolidated minimal-change reviewer returned unconditional PASS on the final scoped source and criterion evidence. |

Frontend scoped coverage after the hydration correction: 47/50 lines (94%) /
40/42 branches (95.23%) across the action, form
and modified header; action and form each have 100% lines. Reports are isolated
in the local temporary directory, preserving unrelated coverage artifacts.

Browser limitations: the machine lacks Playwright's bundled browser; the same
tests ran with installed Chrome and Pixel 7 emulation using a temporary config.
Cold development-server navigation/hydration timed out on initial cases.
Affected cases are repeated after warm-up, without retries hidden by the harness.
The added form made the old image test's jump-to-footer assumption invalid;
the test now visits each lazy image and waits for real decoding.

Final browser correction: an immediate click on the server-rendered disclosure
button could be lost before hydration. The button now stays disabled until
React can handle it, using stable client/server readiness snapshots. The unchanged
click/destination assertions pass in both desktop Chrome and Pixel 7 profiles
after this correction (two cases, no hidden retries). The menu test waits for DOM
content rather than unrelated image loading. All eight width/profile checks and
both real-image checks pass; both synthetic Mailpit submissions passed.
Temporary Next output configuration and its added TypeScript includes were
restored; no verification-only runtime setting is left in tracked source.

Final backend coverage: 117/121 statements (96.69% lines) and 22/22 branches
(100%) across the four new modules. The SMTP-unconfigured real-dependency case
uses unique one-second Redis keys; its recheck and the four current-state
architecture cases pass (five total). Integrated OpenAPI matches the baseline,
and the architecture inventory check passes after exact public-route registration.

Consolidated review correction: the inventory generator previously rejected
the new public route. Its exact group is now registered and the generated
310-operation current-state inventory refreshed. The reviewer accepted both
the inventory and hydration corrections and returned final PASS with no local
acceptance criterion pending. Full CI, production build and live provider
readiness remain unclaimed; request closure waits for the separately authorized
commit/push/full-CI/merge stages.

Full-project TypeScript initially failed on unrelated admin route deletions and
in-progress support/payout code. Marketing-only TypeScript passes; no unrelated
source was repaired. Full CI and production build are not claimed.
