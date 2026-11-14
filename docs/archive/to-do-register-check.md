# Archived to-do/register comparison

Compared every item in `to-do.md` with the current `docs/requests.md`; no register edits made. Suggested statuses are recommendations, not authoritative closures.

No matching dedicated REQ row found:

| Item | Suggested status | Reason |
|---|---|---|
| COM-008 | NEEDS ANSWER | Corporate credit/driver liability policy requires owner confirmation; later simplification may supersede it. |
| REP-007 | NEEDS ANSWER | Report-specific retention/withdrawal policy is not the KYC retention request REQ-218. |
| DB-006 | NEEDS ANSWER | Production version and representative volume facts remain external. |
| REL-002 | NEEDS ANSWER | REQ-010/049 provide templates, not production custody/rotation evidence. |
| REL-008 | NEEDS ANSWER | No dedicated backup owner/RPO/RTO/restore evidence request found. |
| TST-006 | TODO, externally blocked | Physical Android/iPhone evidence remains necessary. |
| TST-009 | TODO, externally blocked | Controlled bank settlement evidence is distinct from sandbox checkout. |
| AUD-003 | DEFERRED | Trigger: live advertising adapter; REQ-214 removed audience export. |
| CAM-005 | DEFERRED | Trigger: reproduced double bind/reachability change. |
| MET-005 | DEFERRED / assess supersession | Trigger: both old report flags; REQ-217 replaced reporting. |
| MET-007 | DEFERRED / assess supersession | Trigger: demonstrated lineage harm under current reporting. |
| OFF-004 | DEFERRED | Trigger: supported device matrix or reproduced lock loss. |
| OFF-007 | DEFERRED | Trigger: approved correction/SLA. |
| OFF-009 | DEFERRED | Trigger: native/background authority and device evidence. |
| ONB-001 | DEFERRED | Trigger: deployed enumeration timing measurements. |
| ONB-007 | DEFERRED | Trigger: bypass or explicit stale-list hardening request. |
| ONB-003 | DONE candidate; controller to trace original commit | Existing hard-conflict rule; no dedicated request row identified. |
| AUD-006 | SUPERSEDED candidate | REQ-214 removes the relevant planning/export capability; no dedicated original row. |
| ONB-004 | DONE candidate; controller to trace original commit | Existing vehicle approval-date rule; no dedicated original row. |
| R11 / AUT-004 | DONE candidate; controller to trace original commit | REQ-238 tests cookie logout but does not itself specify the original global revocation implementation. |
| R06 / DB-002 | DONE candidate; controller to trace original commit | Historical migration safety authority; no dedicated original row. |
| R28 / CAM-001 | SUPERSEDED candidate | REQ-215 replaces manual campaign activation with guarded installation approval. |
| R36 / OFF-005 | DONE candidate; controller to trace original commit | Replay-stable per-sample dispositions have no dedicated original request row found. |
| AUT-006 | DONE candidate; controller to trace original commit | Privilege-elevation reauthentication/global revocation has no dedicated original row found. |
| OFF-008 | DONE candidate; controller to trace original commit | REQ-237 concerns Start reconciliation, not the original ambiguous End decision. |
| ONB-008 | DONE candidate; controller to trace original commit | Registration abuse decision has no dedicated original request row found. |
| ONB-009 | DONE candidate; controller to trace original commit | REQ-301/302 enforce activation evidence; original driver setup-link implementation has no dedicated request row found. |
| ONB-005 | DONE candidate; controller to trace original commit | Same-admin verification authority has no dedicated original request row found. |

Items with matching or encompassing request rows:

| Item | Match |
|---|---|
| R17 / TST-007 | REQ-063, REQ-108, REQ-146, REQ-249 (later CI/coverage policy) |
| GOV-002 | REQ-236 / REQ-248 / REQ-313 integration and CI evidence |
| REL-001 | REQ-025, REQ-027, REQ-035, REQ-050, REQ-051; advertising capability supersession REQ-214 |
| TST-003 | REQ-027 / REQ-035 sandbox contracts |
| REL-007 | REQ-010 / REQ-049 templates; REQ-239 environment/TLS bounds |
| AUT-007 | REQ-060 explicitly retains one advertiser login per company |

Timing deviation: the initial identifier/register search preceded the move; this complete semantic reconciliation was finished after `git mv`. File contents were preserved.
