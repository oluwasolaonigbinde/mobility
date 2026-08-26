# Cardvert privacy operating model

Status: **draft build-only control — not legal approval and not authority for
live personal-data use**.

The machine-checkable register is `docs/privacy-register.json`. It is the
W3-00A operating artefact for roles, purposes, candidate lawful bases,
retention dispositions, recipients, subprocessors/regions, notices,
withdrawal, breach responsibilities, and DPIA risks. This document explains
how an operator uses it.

## Gate and authority

`EXT-LEGAL-PRIVACY` is MISSING. The client has been asked for Q26/Q31 wording,
the named privacy owner, retention/DSR decisions, and legal approval; no answer
or evidence has been supplied. The register therefore sets
`live_use_authorized=false`, leaves every legal approval MISSING, and does not
claim that a candidate lawful basis is valid.

Until qualified Nigerian privacy/legal review approves the relevant rows:

- no real-driver GPS or live KYC collection;
- no advertiser heatmap, issued report, retargeting ingestion/display/export,
  or ad-platform activation;
- no production provider or region is treated as an approved subprocessor;
- no draft notice, checkbox, synthetic fixture, or configured threshold opens
  a live-use gate.

The owner-requested Cardvert document proves these inputs were requested only.
It does not clear `EXT-LEGAL-PRIVACY`, `EXT-REPORT-METHOD`, or
`EXT-AD-PLATFORM`.

## Controller and processor allocation

Terrax Media is represented as the proposed business-controller role because
it owns the Cardvert business and the confirmed operating direction. The named
accountable person and legal/compliance adviser are MISSING. The developer is
the platform-operator role during initial pilot support and acts under the
business role's documented instructions; this does not turn the developer into
the legal approver.

Every external hosting, storage, scanner, messaging, monitoring, payment,
disbursement, or ad-platform allocation remains MISSING with `live_use=false`.
The register must be updated with the provider, region, agreement/transfer
control, purpose, data classes and approved owner before that processor handles
live data.

## ROPA and purpose rules

The `purposes` collection is the record-of-processing-activities index. Each
row has a stable purpose ID, data classes, accountable organizational role,
candidate basis plus approval state, retention-class link, recipients, and the
effect of withdrawal or objection.

Operators must apply these rules:

1. Use data only for a registered purpose. A new purpose requires an amended
   DPIA/ROPA row before implementation or collection.
2. Treat each basis as a candidate until its `basis_approval` is no longer
   MISSING and the evidence reference is recorded.
3. Give access only to the named recipient roles through the product's existing
   RBAC and purpose-scoped services. A router role alone is not sufficient.
4. Do not copy raw GPS, KYC, financial plaintext, credentials, or identity data
   into notifications, logs, support chat, tickets, reports, exports, or audit
   metadata.
5. Treat aggregate location output as personal data until a documented,
   approved re-identification assessment says otherwise.
6. Raw location remains service-only: existing analytics, fraud and payout
   services plus the grandfathered heatmap reader until W3-00C migration.
   Operations staff receive only approved non-raw aggregates or incident-state
   evidence; this model creates no staff raw-ping access path.

## Retention and DSR posture

The retention schedule is deliberately complete about what is unknown. Every
registered data class maps to a disposition, but no MISSING period is silently
converted into a live policy. The current 12-month ping setting is synthetic
build configuration, not legal approval. Backup tooling now enforces both a
newest-14 cap and a hard age bound of at most 35 days.

W3-00B's manual operator workflow is defined in
`docs/data-subject-request-runbook.md`. It opens and identity-verifies one
access, rectification or erasure case; inventories subject-linked database
classes; verifies managed objects through the private-storage port; requires
operator evidence for devices, logs, backups and processors; and refuses
completion until all six locations are assessed. Case identity and location
evidence are append-only, retries are fingerprinted, and storage outage or
mismatch fails closed. This is synthetic build capability, not a live DSR,
approved response deadline or legal disposition.

No erasure operation may rewrite immutable money, invoice, receipt, payout,
fraud-review, or audit facts. The W3-00B service refuses to record database or
object erasure while its inventory still finds records. A retained exception
therefore requires an exact configured approval reference; the setting is
blank by default while the legal decision is MISSING. The inventory covers
MNY-09A route-replay hashes explicitly: those hashes are pseudonymous derived
location-linkage data, not anonymous data.

## Notice, consent, and withdrawal

There are no approved notice versions. A later approved notice record must
contain its immutable version, purposes, data classes, wording hash, effective
time, approver/evidence reference, and replacement/withdrawal relationship.

On withdrawal or objection, the operator follows the ordered procedure in the
register: authenticate proportionately; record purpose/version/time; stop new
dependent processing; preserve only an approved exception; open the W3-00B
cross-store request; and provide a safe completion/exception response. If the
system cannot identify an approved notice or exception, live use fails closed.

## Breach register and escalation

Every suspected confidentiality, integrity, availability, misdirection, or
unauthorized-processing event gets a breach-register record even when later
classified as non-reportable. The record contains discovery time/source,
systems, purposes, data classes, subject estimate, regions/processors,
containment, evidence locations, decisions, actors, notifications, recovery,
and closure.

The platform operator contains and preserves evidence. The Terrax business
role is accountable. The named privacy/legal decision-maker is MISSING and
must decide any subject/authority/processor notification with qualified
Nigerian advice. No statutory deadline is invented in this artefact.

## DPIA treatment

The DPIA risk register covers surveillance, sparse-cell re-identification,
route-to-identity function creep, measurement/ROI overclaim, over-retention,
sensitive-data breach, and unapproved cross-border processing. Every residual
risk stays OPEN until its named package control and external approval exist.
Open residual risk blocks live use; it is not a completion claim.

## Rehearsal and change control

The deterministic build rehearsal is recorded in
`docs/privacy-tabletop-w3-00a.md`. It proves that the roles can follow the
draft withdrawal and breach paths without real data. It is not an operator,
client, or counsel sign-off.

Any future approval updates the structured register and this operating model in
the same change, cites the evidence, and reruns the contract tests. Product or
legal changes require the normal decisions/architecture amendment flow; a
provider credential or approval reference never belongs in source control.
