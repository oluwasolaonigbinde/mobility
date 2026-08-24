# W3-00A synthetic privacy tabletop

Date: 24 August 2026

Evidence class: deterministic synthetic build rehearsal. No real person,
location, provider, client approval, legal advice, or notification occurred.

## Participants by role

- Platform operator: simulated incident commander and request coordinator.
- Terrax Media business controller: simulated accountable business role; named
  person remains MISSING.
- Terrax Media legal/compliance adviser: decision role marked MISSING; every
  step requiring this role stopped at the external gate.
- Data subject: synthetic driver `SUBJECT-W3A-001`.
- Processor contacts: none; all providers, regions, agreements, and contacts
  remain MISSING.

## Scenario A — tracking withdrawal and access/erasure request

Synthetic input: the driver withdraws the draft tracking purpose during a
simulated active trip and requests a copy and erasure of their data.

| Step | Expected action and evidence | Result |
|---|---|---|
| 1 | Authenticate proportionately without requesting unrelated KYC; create request ID `DSR-W3A-001` | PASS — synthetic identity check and request ID recorded |
| 2 | Look up notice/purpose/version and approval | FAIL CLOSED AS DESIGNED — approved notice version and basis are MISSING |
| 3 | Stop new tracking and dependent live advertiser/retargeting output; preserve queued data from further use pending disposition | PASS — required operating decision identified; no real tracker or data was used |
| 4 | Inventory DB, objects, device queue, logs, backups, processors, immutable money/audit exceptions, and route-replay hashes | PARTIAL BY DESIGN — locations and exception questions enumerated; W3-00B and Package 4 storage dependencies are incomplete |
| 5 | Obtain privacy/legal decision on erasure versus immutable financial/audit evidence and processor propagation | BLOCKED — named adviser, approved rule, providers and contacts are MISSING |
| 6 | Reply with completed actions and exact approved exceptions | BLOCKED — cannot claim completion before W3-00B and legal approval |

Outcome: the procedure stops live use instead of treating missing wording or a
checkbox as consent. It preserves the complete W3-00B work rather than
pretending cross-store erasure ran.

## Scenario B — suspected raw-route disclosure

Synthetic input: an operator reports that a link may have exposed one driver's
raw route outside its purpose-authorized service.

| Step | Expected action and evidence | Result |
|---|---|---|
| 1 | Open breach ID `BREACH-W3A-001`; record discovery, systems, purpose, data classes and reporter | PASS — synthetic register shape exercised |
| 2 | Disable advertiser/Module-G output, revoke affected access/credentials, preserve minimum forensic evidence outside chat/tickets | PASS — containment order and redaction rule exercised; no real system changed |
| 3 | Identify affected subjects, processors, regions, time range and propagation without duplicating raw routes | PARTIAL BY DESIGN — subject method defined; providers/regions are MISSING |
| 4 | Privacy decision-maker assesses severity and required subject/authority/processor notification | BLOCKED — named qualified adviser and approved notification rule/deadline are MISSING |
| 5 | Track eradication, recovery, processor confirmation and lessons learned | BLOCKED — no live processor or incident exists; closure cannot be fabricated |

Outcome: containment is immediate, but legal notification and closure remain
fail closed. The rehearsal deliberately does not invent a Nigerian statutory
deadline or a processor contact.

## Gaps carried forward

- `EXT-LEGAL-PRIVACY`: named owner/adviser, approved notices and bases,
  retention/DSR decisions, breach notification rules.
- W3-00B: cross-store DSR dry run and approved retention schedule.
- W2-02E: object/KYC purge and incident operations.
- W3-00C: central disclosure controls for every advertiser output.
- W3-00D/E and `EXT-REPORT-METHOD`: safe measurement contract and immutable
  runs before issued reporting.
- Every processor/provider/region/contact remains MISSING until separately
  approved.
