# Prompt 7 — errors, gates and state transitions audit

## Provenance

- Reviewer: Claude Opus 5, High effort
- Audited source: `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`
- Mode: isolated-worktree, read-only source audit
- Controller capture: 9 September 2026

## Executive result

The backend provides a rich typed error contract, but most frontend consumers
reduce it to a raw message or an unhandled page error. Expected business states,
recoverable conflicts and infrastructure failures therefore look alike to users.

## Confirmed cross-cutting findings

1. The shared API client throws typed `ApiError` for every non-OK response, yet most
   server actions return only `error.message`. `code`, structured `details`, field
   locations, request correlation and retry metadata are rarely used.
2. Expected 401 expiry during a mutation has no shared reauthentication flow that
   preserves the user's intent. Read-time auth handling does not solve lost form or
   action context.
3. Expected 403 governance, privacy and maker/checker states can replace an entire
   page or render as a generic red error rather than a stable blocked state with an
   authorized next action. This broadens the already accepted `PB-12` beyond the
   advertiser report pages.
4. Server-side validation locations are discarded, so errors cannot reliably attach
   to the user-visible field that needs correction.
5. Stale-write 409 details are discarded. Some tests assert local mock copy rather
   than the production error contract, so they can stay green while the real UI
   loses conflict/recovery guidance.
6. `Retry-After` or equivalent retry timing is handled on login but not through a
   general action/read presentation contract.
7. The public driver application maps distinct API failures to one “service
   unavailable” message, preventing useful correction of validation, expired-code
   or conflict states.
8. The batch API uses a separate raw-fetch path that does not preserve the normal
   typed code/status/request-id behavior.
9. Commercial action errors are placed in a query parameter and rendered on the
   campaign page. Although React escaping limits script injection, error content is
   unnecessarily persisted into browser history and may leak through logs or
   referrers.
10. Internal codes, raw field names, snake-case enums and provider/database language
    regularly reach users. This reinforces `CPY-002` and `CPY-003` rather than
    creating one issue per string.
11. The repository has one root `error.tsx` for a broad route tree and many pages
    without section-level degradation. One failed dependent read can erase otherwise
    usable navigation or work queues.

## Recommended product contract

A later implementation should prefer one shared classification layer for auth,
permission/business gate, validation, conflict, rate-limit, unavailable and unknown
errors; reusable state notices; section-level boundaries where partial data is
useful; and a single action-state shape that preserves safe structured details.
This is a bounded shared contract, not authority to expose raw backend details or
log every denial.

## Calibration

- The reviewer's P0 severity for broad error handling is reduced to P1 unless a
  specific path proves immediate security, privacy, safety or irreversible money
  harm.
- Automatic audit events for every 401/403 are not admitted; security logging must
  follow the threat model and avoid sensitive/noisy event capture.
- Backend error changes are unnecessary unless a named frontend state lacks safe
  structured authority. The primary defect is consumption and presentation.
