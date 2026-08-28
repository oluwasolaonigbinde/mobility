# W4-04B-P1 handover preparation

Status: **PREPARATION ONLY**.

| Activity | Repository state |
| --- | --- |
| Handover | NOT PERFORMED |
| Rehearsal | NOT PERFORMED |
| Controlled pilot | NOT PERFORMED |
| Owner/client acceptance | NOT PERFORMED |
| Credential transfer | NOT PERFORMED |
| Live activation | NOT PERFORMED |

This provider-neutral pack indexes integrated evidence and prepares role,
support, risk, credential-custody, and roadmap records for later authorized use.
It supplies no person, provider, account, domain, credential, production value,
approval, support commitment, or operating authority. The database, release
state, audit history, protected operating record, and `docs/progress.md` remain
authoritative; these templates do not replace them.

## Documentation index

| Domain | Current sources | What the sources establish | What remains unclaimed |
| --- | --- | --- | --- |
| System | [Project status](../../README.md#project-status), [MVP contract baseline](../../README.md#mvp-contract-baseline), [OpenAPI snapshot](../api/openapi.snapshot.json) | The integrated FastAPI/PostGIS, worker, Next.js, role, and contract surfaces. | Deployment, production configuration, and live use. |
| Release | [Release operations](../w4-03a-release-operations.md#deterministic-deploy-and-retry-contract), [release-preparation evidence](../pkg-08-w4-03a-preparation.md#delivery-contract), [provider-neutral topology](../runbook.md#provider-neutral-pre-production-topology) | Fail-closed preflight, release identity, forward migration, backup, restore, and previous-image recovery preparation. | Client-owned environment, external rehearsal, live DNS/TLS, or release acceptance. |
| Training | [Training entry point](../training/README.md), [role-task inventories](../training/role-task-inventories.md), [operator procedures](../training/operator-procedures.md) | Actual admin, advertiser, driver, privacy, KYC, fraud, payout, reporting, and incident entry points and boundaries. | Facilitated rehearsal, attendance, competence, or user acceptance. |
| Pilot operations | [Pilot-operations entry point](../pilot-operations/README.md), [operations pack](../pilot-operations/operations-pack.md), [synthetic exercises](../pilot-operations/synthetic-exercises.md), [synthetic pilot journey](../pkg-08-w4-03b-synthetic-journey.md#exact-live-boundaries) | Provider-neutral observation, rollback, replay, incident, evidence, and correlated synthetic journey preparation. | Monitored pilot activity, real telemetry, real providers, or pilot receipt. |
| Privacy and security | [Privacy operating model](../privacy-operating-model.md#gate-and-authority), [privacy register](../privacy-register.json), [DSR runbook](../data-subject-request-runbook.md#safety-rules), [secret rotation](../runbook.md#secret-rotation) | Build-only privacy controls, fail-closed DSR handling, breach responsibility, and secret-rotation constraints. | Legal approval, named privacy authority, real personal-data use, or credential custody. |
| Money and payout | [Payout operator procedure](../training/operator-procedures.md#payout-operations), [payout replay preparation](../pilot-operations/operations-pack.md#domain-payout-replay), [provider-neutral pilot money boundary](../pkg-08-w4-03b-synthetic-journey.md#exact-live-boundaries) | Immutable money lineage, separated maker/checker/reconciler duties, retry identity, and zero-provider-action synthetic preparation. | Provider submission, settlement, paid finality, production rates, or bank custody. |
| Reporting | [Measurement methodology](../measurement-methodology.md#claims-hierarchy), [governed maps/report evidence](../pkg-08-w4-02a-governed-maps-report.md#delivered-contract), [bounded issuance evidence](../pkg-08-w4-02b-bounded-issuance.md#delivery-contract), [report replay preparation](../pilot-operations/operations-pack.md#domain-report-replay) | Reproducible Campaign Performance Analysis, gated conditional ROI, disclosure-safe maps, immutable CSV/PDF issuance, and replay boundaries. | Approved live method, legal authority, production basemap, real report, or ROI claim. |
| Incident and recovery | [Recovery rules](../w4-03a-release-operations.md#recovery-never-downgrade), [incident playbooks](../w4-03a-release-operations.md#incident-playbooks), [database restore](../runbook.md#restore), [privacy breach escalation](../privacy-operating-model.md#breach-register-and-escalation) | Forward-schema recovery, isolated restore, fail-closed incident paths, and evidence/redaction requirements. | Live incident response, destructive restore, legal notification decision, or incident closure. |

External and deferred state is transcribed in
[the risk register](external-and-deferred-risks.md) from the
[programme external register](../progress.md#external-prerequisite-register).
Only the programme controller may change that authority.

## Prepared artifacts

- [Roles and responsibilities](roles-and-responsibilities.md) — placeholder-only
  RACI skeleton and decision boundaries.
- [Support, SLA, and escalation](support-sla-escalation.md) — qualitative
  support flow and proposed, unapproved SLA fields.
- [External and deferred risks](external-and-deferred-risks.md) — exact current
  external/deferred state with effects and closure evidence needs.
- [Credential handover checklist](credential-handover-checklist.md) — custody,
  rotation, revocation, recovery, and evidence template containing no values.
- [Post-MVP roadmap](post-mvp-roadmap.md) — integrated, external/live, and
  post-MVP lanes without dates or commitments.

## Deterministic audit

From the repository root:

```sh
python3 scripts/validate_w404b_handover_preparation.py
```

The audit reads repository files only. It validates local paths and fragments,
required domains and placeholders, proposed-only SLA fields, credential safety,
exact external/deferred parity, roadmap placement, and false completion/live
claims. A pass proves only internal preparation consistency.
