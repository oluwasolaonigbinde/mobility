# ADR 014 — R14-A production-PWA capability and protocol contract

- **Status:** Candidate for Fable integration; R14-A remains `TODO`
- **Date:** 2026-08-16
- **Authority:** `docs/progress.md` R14-A; architecture §1/§9/§23/§30/§35; D15, D16, D18/Q10
- **Executable probe:** authenticated `/driver/capabilities`
- **Contract:** `r14-a-v1`; backend protocol remains `d15-d16-v1`

## Decision

The pilot driver client is an installable, standalone, **foreground-only** PWA. The driver explicitly starts and ends a server trip. During capture the document must remain visible and hold all of these local guarantees:

1. Screen Wake Lock;
2. a usable foreground geolocation grant;
3. a working IndexedDB durable queue;
4. exclusive Web Locks ownership for the tracking writer; and
5. the existing Next.js BFF httpOnly-cookie session, revalidated through the existing backend `/api/v1/me` contract.

The visible health vocabulary is `active | degraded | stopped`:

- `active`: Start/capture/End prerequisites have been proven for the current foreground state;
- `degraded`: a probe is incomplete or a recoverable condition blocks some action; and
- `stopped`: an actual denial, revocation, missing primitive, storage/lock/session failure, or unknown visibility makes capture unsafe.

On the probe page this vocabulary describes **readiness evidence only** — the
probe sentinels are released before assessment, so no wake lock is held, no
writer lock is owned and no trip is active while probing. The driver-visible
`active` during real tracking is a different, stricter claim: a runtime
consumer must feed the same contract live held-state (`wakeLock`/`webLocks`
from actual lock ownership, release events mapping to `released`/`contended`)
and `activeTrip` from the server trip state. Offline/unavailable-session
capture continuation is authorized only while `activeTrip` is true; the probe
page always passes `activeTrip: false`.

No timer, service worker, instruction-only keep-awake step, browser-specific exception, or “best effort” path may claim hidden/background GPS. Visibility loss pauses capture. Native background execution, native credentials, attestation, push and store release remain Phase 2.

## Candidate device matrix

Support is capability-gated, not user-agent-gated. R14-B records the exact physical builds that pass.

| Runtime | R14-A disposition | Conditions |
| --- | --- | --- |
| Android Chrome installed PWA | Candidate supported | HTTPS; scoped manifest/service worker; standalone mode; foreground location; Screen Wake Lock; IndexedDB; exclusive Web Locks; valid BFF session. |
| iPhone Safari “Add to Home Screen” web app | Candidate supported | The same gates; no Safari exception or manual keep-awake fallback. |
| Android/iOS browser tab | Degraded/probe-only | Start and capture blocked because the pilot requires the installed PWA. An owning healthy tab may still perform safe End. |
| In-app browser, embedded webview, desktop, untested alternate browser | Rejected for pilot tracking | Requires the complete capability contract and later physical evidence before admission. |
| Any runtime missing location, Screen Wake Lock, IndexedDB or Web Locks | Rejected | Start/capture fail closed. Storage or writer-lock failure also blocks End from that tab because its watermark cannot be trusted. |

A passing version string alone never authorizes a device.

## Capability contract

| Surface | Supported | Degraded | Rejected / fail-closed action |
| --- | --- | --- | --- |
| Installability | Secure context, linked `/driver` manifest, registered scoped service worker, standalone mode. | Worker not yet observed or regular browser tab; probe remains available, Start/capture blocked. | Insecure context, missing manifest or unavailable service-worker API. |
| Screen-on | Explicit user gesture acquires Screen Wake Lock; tracker holds it while visible. | Not yet probed. | API unavailable, request denied, or held lock released: pause capture; reacquire only after visible-state checks. |
| Visibility/background | `document.visibilityState === "visible"`. | Hidden/backgrounded: report degraded and pause capture. | Unknown visibility. Any claim of background capture is a contract violation. |
| Location | Explicit one-shot foreground probe succeeds; position is discarded. | `prompt`/unprobed blocks Start. Permissions API “granted” alone is not proof. | Denied, revoked after grant, API absent, timeout/unavailable: stop capture. |
| Network/offline | Online for Start/End and session validation. | An already-active, visible trip may continue **durable local queueing** offline. Start and server End remain blocked. Offline reload may show the existing fallback but cannot claim active tracking. | Storage/queue failure; never switch to memory-only or Background Sync assumptions. |
| Reload/recovery | Pending pings and cut batches survive close/reopen with order, counters, payload and retry key unchanged. | Recovery/drain in progress. | Any loss of queue state, watermark or stable retry identity. |
| IndexedDB | Isolated write, reopen, read and delete pass. | Unprobed. | API unavailable, private-mode/policy/quota/transaction failure, or mid-trip write failure: stop capture; block Start/End in that tab. |
| Web Locks | Exclusive lock acquired; nested `ifAvailable` request is refused while held. | Unprobed. | API absent, request denied, contended or ownership lost: this tab neither captures nor Ends. No localStorage mutex fallback. |
| BFF session | Existing guarded page revalidates the cookie-backed session through `/api/v1/me`; browser JavaScript receives no bearer token. | Offline/provider error: retain durable data and block new Start/server End; an already-active foreground trip may keep queuing. | Expired/revoked/redirected session: stop capture and require explicit re-authentication. |
| Start | Online + installed standalone + visible + valid session + location + wake lock + queue + exclusive lock. Server Start must succeed before any capture. | Any prerequisite unprobed. | Any rejected prerequisite; never create a local-only trip. |
| End | Owning lock + healthy queue + valid online BFF session. Stop capture, atomically cut pending pings, retry stable batches, then submit the D15 watermark. | Offline/session unavailable: keep trip and queue recoverable; do not claim server End. | Storage/lock/session invalid: the tab cannot vouch for its watermark. Location/wake loss does not by itself remove safe End. |

## Start, failure and End ordering

**Start:** prove install/visibility/storage/lock/location/wake/session → call existing server Start → only after the active trip returns may the foreground watch persist pings.

**Visibility, permission, wake-lock, lock or storage loss:** stop the watch immediately; never synthesize a position; retain already-durable data; surface the exact code; resume only after visible-state re-probes; never mint a second writer or retry key.

**End:** only the lock-owning tab stops capture → atomically cuts pending pings → drains stable batches in cut order → submits `client_batch_count`, `client_ping_count`, `client_complete` through the existing End action. Failed End retains queue/trip state.

`client_complete` remains diagnostic queue-health evidence, not proof of continuous route coverage.

## D15/D16 invariants — no API movement

R14-A adopts the existing backend/OpenAPI/BFF/auth shapes unchanged:

- pings enter IndexedDB immediately;
- batch cut, removal of pending rows and cumulative watermark increments are atomic;
- one idempotency key is minted at cut and reused with the identical payload after reload/retry;
- accepted, duplicate and quarantined acknowledgements permit local deletion;
- terminal 400/409/422 dead-letter that exact batch without rekeying; retryable failures retain it;
- Web Locks provide one writer;
- server lifecycle remains `active → ended → sealed`; money starts only after `sealed`;
- seal predicate is server batch count ≥ `client_batch_count`; ping count and completeness are diagnostic;
- satisfied watermark may seal immediately; otherwise configured grace sweep seals;
- `ended` is the bounded late-data window and does not require the assignment still to be active;
- post-seal batches are preserved in quarantine with live-batch idempotency;
- audited apply/discard remains serialized; apply requires initial payout, names affected Lagos days, never auto-recomputes money; and pre-seal analytics are not reused for money.

Architecture §9 baselines stay byte-identical: `openapi.json`, `frontend/src/lib/api/schema.d.ts`, and `docs/api/openapi.snapshot.json` do not move.

## Threat model

In scope: accidental/adversarial multi-tab writers; reload/process death/response loss; offline/reconnect; permission denial/revocation; visibility/background transitions; wake-lock release; IndexedDB absence/quota/transaction failure; stale session; duplicate/terminal retries; seal-boundary races; and misleading active/background UI claims.

Out of scope: proof that the branded vehicle rather than the phone moved; GPS spoofing/rooted devices; native process/reboot/background behavior; native secrets/attestation/push/store release; measured completeness, latency, accuracy or battery; real driver/GPS data; backend/auth redesign.

## Probe harness

`/driver/capabilities` is inside the existing driver role layout. It performs no Start, End, ping upload or backend mutation and never requests location on load.

Passive observations: secure context, manifest, service-worker registration, standalone mode, online state and visibility. Button-driven probes:

- **Storage + queue:** unique isolated DB, synthetic `(0,0)` fixture, close/reopen, stable payload/key, retry attempt and dead-letter removal, then database deletion;
- **Web Locks:** exclusive acquisition plus nested contention proof;
- **Screen Wake Lock:** acquire and immediately release;
- **Location:** one foreground fix, discarded completely;
- **BFF session:** no-store fetch of the existing guarded capability page, reusing the current layout and `/api/v1/me` validation.

The redacted JSON report contains browser-reported metadata, states, decisions and protocol constants only—never coordinates, trip IDs, tokens or backend payloads. Browser metadata is evidence metadata, not authorization.

Automated tests cover every environment-independent state/action mapping, denial/revocation, offline queue policy, storage/lock/session failure, probe helper outcome and the complete D15/D16 constant. Playwright proves no location prompt occurs before the explicit button and exercises the authenticated harness with deterministic primitives.

## R14-A / R14-B boundary

This ADR and harness freeze an executable candidate contract; they do **not** complete R14-A or supply R14-B evidence. Fable still owns:

- exact Android and iPhone device/OS/browser build records;
- installed-PWA Start → visible capture → End → seal → worker payout journey;
- physical denial/revocation, hidden/background, reload, offline/retry, storage and lock failure evidence;
- no acknowledged loss/duplication proof;
- completeness, synchronization latency, accuracy and four-hour battery measurements;
- BFF expiry/revocation recovery under real device conditions; and
- independent PWA, security, architecture and data-loss reviews.

Until those gates pass and Fable reconciles authority documents, `docs/progress.md` must keep R14-A `TODO` and must not claim device support.
