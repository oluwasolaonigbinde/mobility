# Parked client, policy, and external follow-ups

This file keeps work that cannot be completed truthfully from the repository
alone. These items are outside the active Cardvert engineering-remediation
queue and do not block independent product or engineering bug fixes. Nothing
below is claimed complete, waived, or supplied.

## Client, business, or legal decisions

- `AUD-006` — decide which campaign lifecycle states may be linked to planning
  sources, including historical analysis.
- `COM-008` — supply the corporate-credit ceiling/facility and driver-liability
  policy, recorder/approver separation, and legacy/retry/concurrency/audit
  treatment.
- `ONB-003` — decide how duplicate NIN, normalized phone, and bank-account
  matches are handled.
- `ONB-004` — set the maximum vehicle-approval horizon and renewal relationship
  to document expiry.
- `REP-007` — approve lawful report retention, withdrawal/tombstone, backup,
  and presigned-link expiry/revocation rules.

## Developer or technical policy intentionally parked

- `R17 / TST-007` — define exact backend/frontend coverage paths, metrics,
  floors, changed-code base selection, and ratchet policy. This is CI policy,
  not a currently demonstrated product-runtime defect; D27 deliberately parks
  it until current runtime product and engineering defects are complete.

## External systems, facts, or evidence still required

- `DB-006` — production PostgreSQL/PostGIS version and representative data
  volumes.
- `GOV-002` — final immutable exact-commit green CI evidence after the build is
  stable.
- `REL-001` — selected payment, disbursement, and advertising providers,
  accounts, specifications, and sandbox contracts.
- `REL-002` — selected production KMS/vault and custody/rotation specification.
- `REL-008` — backup owner, scope, cadence, protected destination, RPO/RTO, and
  restore evidence.
- `TST-003` — real provider sandbox/live-contract evidence.
- `TST-006` — physical Android/iPhone lifecycle, storage, permission, battery,
  network, and GPS evidence.
- `TST-009` — controlled low-value provider/bank settlement evidence.

## Deferred until a real trigger exists

- `AUD-003` — revisit before enabling a live advertising-platform adapter.
- `CAM-005` — revisit if a double bind is reproduced or review-state
  reachability changes.
- `MET-005` — revisit before enabling both live report flags.
- `MET-007` — revisit if consecutive-period lineage harm is demonstrated.
- `OFF-004` — revisit after a supported-device matrix exists or lock loss is
  reproduced on a supported target.
- `OFF-007` — revisit after automatic correction or an enforceable operational
  SLA is approved.
- `OFF-009` — revisit with native/background authority and physical-device
  evidence.
- `ONB-001` — revisit if deployed timing measurements establish an enumeration
  signal.
- `ONB-007` — revisit if the existing write gate can be bypassed or stale-list
  hardening is deliberately requested.

## Decisions removed from the parked list on 2 September 2026

- `R11 / AUT-004` — the project owner decided that logout signs the user out on
  every device. Implementation must rotate durable session authority, clear the
  current cookie, and prevent an in-flight refresh from restoring a session.
- `R06 / DB-002` — engineering may add the narrowly reviewed safety guards to
  historical downgrade bodies and update their authority documentation; this
  is development-time migration safety, not a client product decision.
- `R28 / CAM-001` — existing client authority already says an administrator
  performs final campaign activation (`D18/Q15`); planning must derive the
  actor and readiness behavior from that decision rather than ask again.
- `R36 / OFF-005` — engineering may use the already reviewed durable
  migration/model/signing design for replay-stable per-sample dispositions;
  this is integrity implementation, not a client product decision.
- `AUT-006` — privilege elevation requires password reauthentication and global
  session revocation before elevated authority is usable.
- `OFF-008` — an ambiguous End stops capture and retries the identical durable
  End request until authoritative confirmation.
- `ONB-008` — registration abuse uses per-IP and normalized-identity limits,
  non-revealing responses, and operational alerts rather than a global switch.
- `REL-007` — bundled and managed PostgreSQL/Redis are both supported, while
  production requires TLS, authentication, explicit hostnames, and supplied
  secrets.
- `ONB-009` — an authorised Cardvert admin initiates activation only after the
  driver is fully approved; the driver completes a short-lived, single-use
  setup link to choose the password and atomically activate the account.
- `AUT-007` — every advertiser login belongs to exactly one advertiser company;
  multi-company agency access and silent company selection are not supported.
- `ONB-005` — one Cardvert admin may verify the payout account and approve the
  same driver's person/payee and vehicle evidence, with each action preserved
  in immutable audit/evidence.
