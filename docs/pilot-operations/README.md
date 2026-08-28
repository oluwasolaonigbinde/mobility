# W4-03C-P1 controlled-pilot operations preparation

This directory is a provider-neutral preparation pack. It is not an operating
authority, approval record, production configuration, or pilot receipt.
W4-03C remains incomplete and externally blocked. No monitored controlled pilot
has been performed.

Use the [operations pack](operations-pack.md) to prepare observation, stop,
rollback, replay, incident, and evidence records. Use the
[synthetic exercise matrix](synthetic-exercises.md) only in a local repository
test environment. The templates point back to integrated state and procedures;
they never replace database rows, release state, audit history, or the following
authoritative material:

- [W4-03A release operations](../w4-03a-release-operations.md) for readiness,
  recovery, observability, and incident rules;
- [the repository runbook](../runbook.md) for worker, lifecycle, storage, KYC,
  recovery, and common-failure procedures;
- [Package 8 release preparation evidence](../pkg-08-w4-03a-preparation.md) and
  [synthetic pilot journey](../pkg-08-w4-03b-synthetic-journey.md);
- [bounded report issuance](../pkg-08-w4-02b-bounded-issuance.md) and
  [local load/reproducibility evidence](../pkg-08-w4-03b-load-reproducibility.md);
- [privacy operating model](../privacy-operating-model.md) and
  [data-subject request runbook](../data-subject-request-runbook.md).

## W4-03C external/live gate snapshot

This table transcribes the W4-03C checklist dependencies in `docs/progress.md`.
It does not change them. Only the programme controller may update their states.

| Gate | Current state |
|---|---|
| EXT-DISBURSEMENT-PROVIDER | MISSING |
| EXT-SETTLEMENT-BANK | MISSING |
| EXT-RM2-POLICY | PRESENT |
| EXT-STORAGE-PROVIDER | MISSING |
| EXT-MALWARE-SCANNER | MISSING |
| EXT-KMS-CUSTODY | MISSING |
| EXT-PHONE-OPERATOR | MISSING |
| EXT-EVIDENCE-POLICY | MISSING |
| EXT-LEGAL-PRIVACY | MISSING |
| EXT-UPLOAD-POLICY | MISSING |
| EXT-PAYMENT-PROVIDER | MISSING |
| EXT-BUDGET-POLICY | MISSING |
| EXT-Q28-COMPANY | MISSING |
| EXT-COMMERCIAL-VALUES | MISSING |
| EXT-CAMPAIGN-BUDGET-SCOPE | MISSING |
| EXT-BASEMAP | MISSING |
| EXT-REPORT-METHOD | MISSING |
| EXT-AD-PLATFORM | MISSING |
| EXT-RELEASE-ENV | MISSING |
| EXT-STAGING-APPROVAL | MISSING |
| EXT-PILOT-FACTS | PRESENT |
| EXT-PILOT-PERMITS | MISSING |
| EXT-OPERATIONS-OWNER | MISSING |

`PRESENT` means only that the registered programme fact exists. It does not
supply a provider, owner, account, permit, legal/commercial approval, or live
operating authority. Every `MISSING` row remains a live gate.

## Deterministic audit

From the repository root, with the repository Python environment active:

```sh
python3 scripts/validate_w403c_pilot_preparation.py
```

The audit checks the six-domain contract, links, local command targets, exact
W4-03C gate states, stop/evidence fields, placeholders, and false live or
completion claims. Passing it proves only that this preparation pack is
internally consistent with the integrated repository paths it cites.
