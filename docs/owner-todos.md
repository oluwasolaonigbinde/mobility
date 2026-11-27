# Owner to-dos

Things only the owner can do or decide, kept in one place so none is lost
(REQ-345). The work register is still [requests.md](requests.md): every item
here points to its request where one exists, and this file adds nothing that
is not also recorded there or in [client-decisions.md](client-decisions.md).
Agents add an item when it comes up, tick it off with the date when it is done,
and remind the owner of the open ones at each update. Last updated 27 Nov 2026.

## Before real drivers use the Android app (REQ-343)

- [ ] **Permanent signing key.** Decide who holds the release key for the
  real app. Test builds use a test-only key that must never reach real
  drivers. Updates only install over an app signed with the same key, so this
  is chosen once.
- [ ] **Play Store account, app name and package ID.** Deferred by the owner
  on 27 Nov. Working placeholders: "Cardvert Driver",
  `com.terraxmedia.cardvert.driver`, Terrax Media's account.
- [ ] **Play listing extras.** A privacy policy page, plus a short video
  showing location tracking with the ongoing notification (Google asks for
  this for apps that track location from a notification-backed service).
- [ ] **The client's own domain for the app.** Test builds talk to
  `23-88-42-94.sslip.io`; real drivers need the client's domain (see Domain
  below). Email links open the app only once the domain and permanent key exist.
- [ ] **Read the app-only wording.** Lines written for the app, not taken from
  the website (screen-off tracking, sign-out refusals, battery advice, phone
  check). They will be listed in the stage 1 summary.
- [ ] **Phone test of each stage** on your Android phone, using the test APK
  link posted at each stage.

## Domain (REQ-033, REQ-043)

- [ ] **Confirm the name.** Cardvert goes on the apex `terraxmedia.com`
  (owner, 21 Nov), with `www` and `s3`, on Hetzner `23.88.42.94`.
- [ ] **DNS access.** Whogohost login was blocked on 23 Nov (its codes were
  refused). Log in yourself, or set the records by hand, or get the login code
  to the agent. Keep the existing Zoho email records. Paused by the owner on
  25 Nov.
- After DNS: the agent sets up Hetzner's Caddy and env, and adds the domain to
  the MapTiler key's allowed origins.

## Before go-live (paid services and live money)

- [ ] **Live Paystack keys** and the real-transfer proof (W2-01C). Also on
  Paystack:
  - turn on 2FA and change the password;
  - turn transfer OTP off (Cardvert has no OTP step);
  - set the support/dispute email (suggested terraxmediacompany@gmail.com);
  - decide who tops up the transfer balance, and how often;
  - invite the developer.
- [ ] **Email.** Unblock Zoho (parked 21 Nov), publish DMARC, add Postmark's
  DKIM and Return-Path, or pick one provider. The Gmail access setup was paused
  on 25 Nov.
- [ ] **Feedback button retention.** How long `/feedback` notes and
  screenshots are kept, before any production use (D172/D173).

## Decisions and approvals waiting

- [ ] **REQ-337 / REQ-339 (PR #50).** Browser check on Hetzner first, or merge
  now; then the Contabo deploy.
- [ ] **REQ-341 copy fixes (PR #51).** Approve the payment-mismatch wording
  ("Transfer recorded but not applied: the amount doesn't match the expected
  amount."), and the 24 copy questions still open.
- [ ] **REQ-342 design skill.** Approve PRODUCT.md, then commit and merge.
  This work is on the laptop.
- [ ] **REQ-323.** Triage of the 28 archived to-dos, and the five decisions:
  REP-007 report retention, DB-006, REL-002 secrets, REL-008 backups.
- [ ] **Records branch for REQ-327 / REQ-328** (Moniepoint, corporate credit).
  This work is on the laptop; OK to commit and merge.
- [ ] **Firefly gap analysis.** Record it as a request? Answer the eight client
  decisions in its section 1.7, and delete the old Claude doc yourself.
- [ ] **Contabo preview.** Turn on live demo cars there? When to retire it?
  The map switch back to OpenFreeMap (REQ-344) has to be deployed to Contabo
  from the laptop, because this server's account can't touch it.
- [ ] **MapTiler account.** No longer used after REQ-344; close it if you like.

## Account housekeeping

- [ ] **Change the Hetzner password** (it was shared in chat).
- [ ] **Paystack test webhook.** Point it at the Contabo preview's
  `/api/v1/webhooks/paystack`.

## Done

- 27 Nov 2026: MapTiler Flex plan no longer needed; the map goes back to free OpenFreeMap (REQ-344).
