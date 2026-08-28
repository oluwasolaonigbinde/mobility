# PKG-07 W4-01D release rehearsal evidence

- Date: 2026-08-28
- Base: `43b98940298e2002f22365d2bf7da06a7d0d05c0`
- Branch: `feat/pkg-07-w4-01d-pwa-earnings-disputes-release`

## Delivered contract

- Jobs distinguish a verified empty campaign history from unavailable campaign,
  evidence or journey authority.
- Earnings render the backend's canonical summary fields and recent ledger rows
  independently. Only pending trip entries joined to a current public hold in
  `assessment_pending`, `under_review` or `issue_confirmed` display as held;
  `review_cleared` does not.
- Trip detail uses the existing `payout_v3` breakdown and public fraud-hold
  projection. If current hold authority cannot be verified, the amount and
  dispute controls are withheld.
- Dispute submission preserves the existing owner-scoped endpoint, normalized
  exact-retry behavior and backend authorization/idempotency. Session rejection
  produces sign-in guidance without retrying or exposing backend detail.
- In-app notifications remain sanitized server projections. Query state is
  user-scoped and is hidden/removed after offline, revocation or shell disposal;
  mutations are unavailable offline.
- The service worker caches only hashed `/_next/static/` resources. Navigation
  stays network-only and receives an inline `503`, `no-store` unavailable shell
  when offline. Already-rendered campaign, money, hold and dispute authority is
  removed on the browser's offline event and remains hidden after reconnect
  until a fresh navigation reloads server authority. The fallback contains no
  current money, hold, identity or location data.

Unchanged: the W4-01A/B encrypted single-writer queue, foreground-only capture,
watermark/seal protocol and W4-01C governed campaign journey. No tracking,
money, hold, approval, notification or readiness authority was added.

## Adversarial boundary matrix

| Boundary            | Break case                                                        | Expected evidence                                                                                            |
| ------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Money projection    | One summary/ledger/assignment/hold read is absent or fails        | Explicit unavailable view; no amount, empty ledger claim or mutation                                         |
| Hold classification | Pending entry has cleared, missing or another trip's hold         | Remains pending; only the three active public states show held                                               |
| Dispute retry       | Exact normalized request is repeated; changed request follows     | Existing backend row converges; changed payload is `409`; one audit/notice authority                         |
| Identity/tenant     | Revoked token, wrong role, different driver                       | Login/role redirect or owner-hidden `404`; no driver money/history survives Back                             |
| Offline/cache       | Open-page transition, reload/navigation or mutation while offline | Sensitive markup/actions hidden; static-only CacheStorage; `503` unavailable shell; mutation network failure |
| Privacy             | Hold/notification projection contains internal evidence fields    | UI consumes only public reason/dispute/reply and sanitized notice copy                                       |
| Distribution        | Production build on desktop Chromium and iPhone-sized WebKit      | Manifest/icon/scope/session/reload journey passes without live/store claims                                  |

## Observed red/green evidence

The first unchanged-behavior regression run produced four expected failures:
full canonical summary/held projection was absent, provider failure escaped the
Jobs history boundary, cached notifications remained visible offline, and the
offline shell lacked fresh-money/review and non-cacheable `503` semantics.

After implementation, the focused frontend set passes 30 tests across earnings,
trip detail, dispute action/form, campaign history, notifications and the PWA
contract. After the review corrections, the Package 7 frontend aggregate
passes 352 tests across 69 files, plus typecheck, full lint, scoped formatting
and a production build. The
production rehearsal passes once in desktop Chromium and once in
an iPhone 13/WebKit profile. Chromium additionally performs the real offline
navigation and blocked-mutation check; Playwright WebKit's offline network toggle
returns an internal engine error, so that is not reported as WebKit offline proof.

## Reproducible rehearsal

From `frontend/`:

```sh
npx playwright install webkit
W401D_SYNTHETIC=1 npx playwright test e2e/w401d-release-rehearsal.spec.ts --project=chromium --project=mobile-webkit
```

`W401D_SYNTHETIC=1` builds the standalone production app, starts a local
provider-neutral authority simulator on loopback, and runs isolated per-project
driver sessions. The simulator uses only synthetic identifiers and `.invalid`
contact data.

## Closure and external gates

The preserved W4-01C synthetic journey passes in its intended Pixel 7 and
iPhone-sized profiles (two passes and two expected cross-project skips).
Focused backend authority checks pass 48 tests with 30 environment-gated skips.
The clean-context consolidated Package 7 post-build review is `PASS` after it
identified and rechecked open-page offline freshness, reconnect latching,
notification session-cache isolation and simulator contract corrections. The
three §9 API artifacts are byte-stable against the exact base;
`docs/progress.md`, backend code and migrations are unchanged.

Still external/not claimed: physical Android/iPhone installation and update,
representative route/battery/SLO evidence, native signing/store listing/push,
approved staging/distribution, live providers, real GPS, and pilot execution.
