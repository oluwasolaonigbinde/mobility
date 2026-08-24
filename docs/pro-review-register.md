# Advisory Pro review register

Last reconciled against `feat/pkg-02` at
`b9c67463d8cebfe2b1f2a44a115d9a7180e554f1` on 23 August 2026.

## Status and precedence

This register preserves independently reconciled findings from four GPT-5.6
Pro assignments. It is advisory revalidation input, not a work queue, adopted
architecture, decision log, or implementation authorization.

Controllers must first follow `AGENTS.md`: `docs/progress.md` alone controls
package status and order; `docs/architecture.md` and `docs/decisions-log.md`
control adopted design and product decisions; current code and tests control
implementation reality. Read only the active package section and inherited
seams below, revalidate every item against the active base, and adopt only the
smallest change required by the authoritative package contract.

## Package 1 findings inherited by later packages

The useful audit findings and their current dispositions are:

1. **DB clock and terms serialization — RESOLVED in PKG-02 C1 (`309a5a2`).**
   Assignment acceptance and payout-rule publication now share a campaign
   transaction lock and database wall clock.
2. **Accepted campaign payment window — RESOLVED in PKG-02 C1 (`309a5a2`).**
   New payout-v3 bindings freeze nullable campaign windows; legacy provenance
   fails closed, and calculation/correction metadata is value-complete.
3. **Real tracker capability/session/writer lock — DEFERRED to PKG-07 entry.**
   Enforce ADR 014 and stale writer-lock recovery before real GPS/PWA authority.
4. **Terminal ping rejection evidence — DEFERRED to PKG-07 entry.** Preserve
   dead-letter evidence rather than deleting it or overstating completeness.
5. **Populated downgrades 0018–0021 — RESOLVED in PKG-02 C1 (`309a5a2`).**
   Financial authority now blocks destructive populated downgrade.
6. **Corrected driver explanation provenance — RESOLVED in PKG-02 C0
   (`83456c2`, hardened at `4f1f768`).** Eligible and excluded-reason fields
   come from the same newest authoritative recompute and malformed newest
   provenance does not expose stale history.
7. **Adjacent-day correction race — RESOLVED in PKG-02 C1 (`309a5a2`).**
   Overlapping trips lock in stable UUID order before day-cap locks while cap
   allocation remains chronological; neighboring-day half-cent, deadlock,
   stale-loser and retry behavior is covered.
8. **Rollback/restore evidence — DEFERRED to PKG-08/W4-03A.** Current evidence
   proves local configuration, smoke, and database restore contracts only;
   parameterized frontend-image rollback must be executed before it is claimed.

## Package 2 money and payout operations

MNY-08A/MNY-09A/MNY-08B/MNY-08C/MNY-03A and C0/C1 are delivered. The external
Lane B attempt ended without a durable diff because its execution environment
was read-only. The controller recovered the unchanged reviewed sequence
MNY-10A → MNY-10B → MNY-10C → MNY-11A into the writable local workflow. It
must consume the authoritative hold contract at
`3aeb2a55b959e3d5c6b1a489004042075fb9d9ea`.

Preserve these invariants:

- Release now requires the exact successful-current assessment plus the
  imported authoritative `hold_active` rule under the existing trip scope.
  Lane B must consume that contract and never introduce another hold predicate.
- Bank/payee details are encrypted behind the adopted provider-neutral port and
  versioned so edits cannot rewrite frozen instructions.
- Batch creation atomically reserves source entries and prevents duplicate
  active instructions. Whole-entry reservation remains adopted unless the
  owner approves partial allocation.
- Lines freeze payee/account version, amount, currency, integrity fingerprint,
  and idempotency identity. Submission is never cash-paid finality.
- Only signed webhook or verified poll evidence reconciles a provider line.
  Ambiguous responses stay reconcilable and are not blindly resubmitted.
- Maker, approver, and reconciler authority remain distinct.
- Paid history and carry-forward debt are append-only and currency-isolated.
- Provider-neutral synthetic work may proceed, but live submission remains
  disabled until `EXT-DISBURSEMENT-PROVIDER` is satisfied.

Avoid speculative balance/source projections, blanket immutability triggers,
raw provider-payload retention, partial-allocation tables, or extra lifecycle
states unless the active implementation proves one is necessary.

## Package 3 commercial and billing

- Freeze accepted quotation/commercial terms; model negotiated deals as
  structured accepted terms, not undocumented exceptions.
- Manual-bank and gateway evidence converge on one receipt/allocation truth.
- Issued invoice net/VAT/gross and receipt corrections are immutable and
  append-only. Real issuance still needs the registered issuer facts.
- Production timing begins when sufficient confirmed allocation authorizes it;
  an expedited waiver ends refund eligibility only when production begins.
- Advertiser spend/liability, driver earnings, and cash paid are distinct;
  fraud-held earnings never create funding headroom.
- Treat legacy `payments` wording as a projection, not a second cash model.

`EXT-BUDGET-POLICY` remains the major registered product input.

## Package 4 files, evidence, and communications

- Use one stored-file lifecycle for upload, validation, scan, quarantine or
  rejection, approval, replacement, expiry, and deletion.
- Approval binds the exact immutable file/evidence version and checksum.
  Activation locks and re-reads current prerequisites so replaced evidence
  cannot inherit stale approval.
- Reuse Package 2's final D17 encryption/key-version port with no plaintext
  fallback or second crypto subsystem.
- Extend the Package 2 notification seam rather than creating another outbox;
  business mutation and logical notification commit atomically with stable
  dedupe and authenticated receipt handling.
- Enforce subject and organisation ownership in services, not router roles
  alone.
- Test tenant isolation, server-observed type mismatch, polyglots and format
  ambiguity, parser/decompression resource bounds, quarantine and safe serving,
  malware, timeouts, retry, and idempotency synthetically.
- Reuse final fraud freshness/replay/hold boundaries for proof challenges.

**Candidate only:** ClamAV is the preferred Package 4 malware-scanner proof of
fit. Evaluate detection, latency, size limits, quarantine, timeout/fail-closed
behavior, signature updates, and operations before adoption. It is not a
dependency or resolved external provider decision.

## Package 5 measurement and privacy

- The current advertiser heatmap/raw-ping path is not an adequate privacy
  boundary. Every later heatmap, report, segment, export and activation passes
  one disclosure-control service with multi-dimensional suppression,
  contributor caps and differencing defence.
- Centralize disclosure/calculation logic; issued results use immutable,
  formula-versioned runs, eligible-universe/proof manifests and append-only
  correction lineage.
- Proof manifests consistently disclose methods, assumptions, limitations, and
  exclusions. Positive allowlists reject person-level identifiers hidden in
  metadata, free text and nested activation payloads.
- Test tenant/export leakage, cohort protection, location minimization,
  tampering, replay, and selective evidence omission.
- Enforce subject and organisation ownership in measurement services, not
  router roles alone. Legal retention controls raw data; reproducibility cannot
  justify indefinite retention or resurrection of purged personal data.

## Package 6 eligibility and offers

- Derive eligibility from approved driver/person, payee, and vehicle state.
- Freeze all money-bearing and operational terms at offer acceptance.
- Reuse Package 2 payee/account versions and hold boundaries.

## Package 7 tracking and disputes

- Reuse R14 and D15/D16 capability, queue, seal, and session contracts; do not
  add a second offline queue, tracking protocol, or public bearer API.
- Complete deferred Package 1 findings 3 and 4 before real GPS/PWA authority.
- Reuse Package 2 fraud evidence, holds, and corrected explanations.
- Preserve synthetic replay, gap, dead-letter, session-loss, duplicate-delivery,
  and correction-history break cases.

## Package 8 reporting and recovery evidence

- Generate reports asynchronously from frozen versioned snapshots. CSV and PDF
  share data, disclosures, assumptions, and correction identity.
- Keep methodology/ROI policy separate from renderer choice; issuance and
  correction lineage must be reproducible.
- Complete Package 1 finding 8 before claiming frontend rollback proof.

**Candidate only:** WeasyPrint is the preferred Package 8 PDF-renderer proof of
fit. Evaluate CSS/fonts, pagination, charts/images, deterministic output,
performance, container packaging, and maintenance before adoption.
`EXT-REPORT-METHOD` remains unresolved by any renderer choice.

## Package 9 release and training

- Train and rehearse the exact accepted candidate with deployment, rollback,
  restore, risk, ownership, and sign-off evidence.
- Distinguish synthetic build proof from real staging/pilot proof; runbook text
  alone cannot close operational evidence.

## Cross-package reuse and rejected complexity

Reuse final Package 2 fraud freshness, replay, hold, account-version,
provider-finality, and debt contracts after they freeze. Reuse existing auth,
audit, idempotency, worker, BFF, and error-envelope conventions. Do not create a
second cash model, hold flag, upload flow, disclosure path, notification system,
or PWA tracking protocol.

External inputs block the stage that truly needs them—usually live use—not
provider-neutral synthetic construction. Pro-proposed filenames, migrations,
schemas, APIs, waves, and slice counts remain navigation ideas until the active
package plan validates them.
