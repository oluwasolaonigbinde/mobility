# REQ-230 pre-push readiness evidence

## Part 2: measurement before source fixes

CI installation uses Python 3.12.14 and `pip install -e ".[dev,static]"` in a fresh virtual environment. Both source exports use that same resolved environment and exact `basedpyright` command, including their committed baselines. No worktree baseline was modified by measurement.

- HEAD `842e4c41`: exit 1, 35 errors, no warnings.
- origin/master `8e509f7f`: exit 0, zero errors or warnings.
- No unbaselined dependency-drift diagnostics detected in the master control. All 35 HEAD diagnostics concern branch source typing; none concerns the new QR/report dependencies. The newer resolved libraries are recorded rather than described as unchanged.
- Raw logs, resolved versions and complete messages: external `req230-tools/{head,master}-basedpyright.log`, `resolved-versions.json`, `part2-initial-errors.json`.

### Resolved tool/library versions

- basedpyright: 1.40.1
- nodejs-wheel-binaries: 24.19.0
- SQLAlchemy: 2.0.55
- pydantic: 2.13.4
- pydantic-settings: 2.16.1
- fastapi: 0.162.0
- starlette: 1.9.0
- redis: 5.3.1
- arq: 0.28.0
- boto3: 1.43.118
- botocore: 1.43.118
- cryptography: 50.0.2
- reportlab: 5.1.0
- ruff: 0.17.2

### Initial counts by file

| File | Errors |
| --- | ---: |
| `app/api/v1/admin.py` | 1 |
| `app/api/v1/campaigns.py` | 1 |
| `app/api/v1/navigation.py` | 1 |
| `app/jobs/worker.py` | 1 |
| `app/services/campaign_enquiries.py` | 1 |
| `app/services/driver_applications.py` | 1 |
| `app/services/driver_review_notifications.py` | 27 |
| `app/services/list_counts.py` | 2 |

### Initial counts by rule

| Rule | Errors |
| --- | ---: |
| `reportArgumentType` | 9 |
| `reportOptionalMemberAccess` | 13 |
| `reportCallIssue` | 2 |
| `reportAttributeAccessIssue` | 11 |

### Complete initial error locations

| File:line:column | Rule |
| --- | --- |
| `app/api/v1/admin.py:183:29` | `reportArgumentType` |
| `app/api/v1/campaigns.py:127:21` | `reportArgumentType` |
| `app/api/v1/navigation.py:43:59` | `reportArgumentType` |
| `app/jobs/worker.py:88:76` | `reportArgumentType` |
| `app/services/campaign_enquiries.py:52:13` | `reportArgumentType` |
| `app/services/driver_applications.py:298:30` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:43:12` | `reportCallIssue` |
| `app/services/driver_review_notifications.py:43:24` | `reportArgumentType` |
| `app/services/driver_review_notifications.py:103:49` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:107:26` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:110:68` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:113:27` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:113:45` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:115:32` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:122:59` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:124:28` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:134:30` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:135:38` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:136:21` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:137:23` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:137:42` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:145:57` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:152:26` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:152:26` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:153:40` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:153:40` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:154:42` | `reportArgumentType` |
| `app/services/driver_review_notifications.py:154:47` | `reportArgumentType` |
| `app/services/driver_review_notifications.py:171:40` | `reportOptionalMemberAccess` |
| `app/services/driver_review_notifications.py:192:62` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:196:74` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:212:28` | `reportAttributeAccessIssue` |
| `app/services/driver_review_notifications.py:212:48` | `reportAttributeAccessIssue` |
| `app/services/list_counts.py:21:12` | `reportCallIssue` |
| `app/services/list_counts.py:21:17` | `reportArgumentType` |

## Part 2: source corrections and verification

- The review-notification errors share the dynamic ID/car model pair and its optional database rows. Type aliases and paired column names describe that relationship once; the existing ownership/purge/current-revision guards justify the subsequent narrowing. No new assertion, exception, access branch or delivery rule was added.
- List filters/counts have explicit SQLAlchemy/UUID types; row pairs build the same count mapping. Response projections use Pydantic `model_validate` for their existing nested data. The continuation token cast follows the existing same-transaction validation/lock. The destination resolver accepts the callable session-factory capability actually used by `OutboxSession`; its money authority is unchanged.
- Exact `basedpyright`: exit 0, zero errors/warnings. Baseline multiset subset proof: 286 → 207 entries, 79 removed, zero added. No ignore, config relaxation, dependency change or CI-command change.
- `ruff check .`: PASS, including the final fixture corrections.
- `python scripts/update_openapi_snapshot.py --check`: PASS; snapshot unchanged.
- Eight focused test files: 56 distinct tests PASS against isolated real PostgreSQL (`cardvert_req230`). Initial collection required the worker's synthetic local Redis URL. Two stale existing fixtures were corrected: derived Finished uses active + past end date and `CAMPAIGN_FINISHED`; the current registry includes `generate_campaign_report` and 21 cron jobs. The integrated run passed 55; the corrected Finished assertion then passed its focused rerun. Raw failure and final logs are retained externally.
- `scripts/verify_preprod.sh --static-only`: PASS. The Windows checkout's unchanged shell scripts were copied with LF endings outside the repository. A local bridge forwarded the script's actual Docker commands to the host CLI; both Compose renders and Caddy validation used repository configuration. Pinned Caddy digest: `sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17`.
- Coverage was collected for the focused run. The destination resolver has 22/22 covered statements and no branches; review notifications have 23/26 covered branches. No product behavior change was needed. Full-suite changed-code/85% sensitive-scope CI enforcement is unchanged and remains a pre-push/merge controller gate; these focused checks do not claim full CI.
- Security source review: **PASS**, `gpt-6.1-sol`, **high**. The reviewer verified same-token locking, recipient ownership, current revisions, purge guards, frozen payout destination and validated response projections. No source correction was required by that review.

External tooling and logs live in `C:\Users\Dell\.t3\worktrees\mobility\req230-tools\`. Docker hold 18:45:40Z–19:21:23Z: `cv-req230` stopped and retained, own lock released; REQ-209 acquired it at 19:21:32Z. Windows Available memory was 1,807 MB at release.

## Part 1: gate cleanup and verification

The controller's frozen progress/requests SHA-256 hashes remain unchanged by the worker. The register keeps 27 external entries after only the three authorized retirements; the handover mirror has 26 after its existing historical package-owner exclusion. The old handover validator's 30-row expectation was stale. All remaining external states are unchanged. The checklist retains 71 rows and 22 PARENT rows.

Combined privacy+money specialist final review: **PASS**, `gpt-6.1-sol`, **high**. Two documentation findings (money separation copy and the G-15 method crosswalk) were corrected and rechecked. The final delta recheck also verified the test authority reader described below. Remaining legal/manual-request/non-KYC/notice/adviser/restoration obligations, the pinned pilot evidence, provider/bank authority, holds/audit/stale checks and independent evidence/credential controls remain intact. No remaining specialist findings.

### A1: explicit retirement-reference allow-list — PASS

Search: `rg -n --no-heading 'EXT-EVIDENCE-POLICY|EXT-PHONE-OPERATOR|EXT-AD-PLATFORM|G-moduleG|PHONE_OPERATOR_EXTERNAL_APPROVED' docs scripts tests frontend`, excluding `docs/archive/**`, `account-access.md` and `tmp/**` at any depth. The audit also rejects newly added retired references in the historical architecture/contract documents. Exactly 17 allowed occurrences remain:

| Allowed file:line | Reason |
| --- | --- |
| `docs/architecture.md:3832` | Unchanged historical v1.70 changelog |
| `docs/architecture.md:3836` | Unchanged historical v1.66 changelog |
| `docs/architecture.md:3840` | Unchanged historical v1.62 changelog |
| `docs/architecture.md:3856` | Unchanged historical v1.46 changelog |
| `docs/delivery-contracts.md:533` | Unchanged W2-03C historical checkpoint evidence |
| `docs/delivery-contracts.md:687` | Unchanged W2-04C/D historical closure evidence |
| `docs/delivery-contracts.md:703` | PKG-05 historical 24 Aug plan restored exactly to HEAD |
| `docs/delivery-contracts.md:809` | Unchanged W3-01B historical checkpoint evidence |
| `docs/delivery-contracts.md:825` | Unchanged W3-01C historical checkpoint evidence |
| `docs/delivery-contracts.md:841` | Unchanged W3-01D historical checkpoint evidence |
| `docs/delivery-contracts.md:895` | Unchanged PKG-05 historical closure evidence |
| `docs/progress.md:796` | Controller retirement note |
| `docs/progress.md:797` | Controller retirement note |
| `docs/progress.md:798` | Controller retirement note |
| `docs/requests.md:88` | Controller REQ-230 retirement scope |
| `tests/test_r59_real_stack_contract.py:112` | Negative assertion: flag absent |
| `tests/test_req216_fixed_limits.py:87` | Negative assertion: flag absent |

### A2, A4 and A6: authority and current documentation — PASS

- The external authority audit compares against HEAD: only the three approved retired identities disappear; all remaining states and every non-narrowed row are unchanged. The pilot-facts Evidence cell is unchanged, as are controller/package statuses and pointers. Frozen controller-file SHA-256 checks pass.
- Legal/manual-request deadlines, redaction and retention exceptions remain unset pending the named adviser. Driver agreement/consent wording (Q26), required disclosures, non-KYC GPS/evidence/backup retention and driver phone/WhatsApp notices/lawful bases remain required. KYC alone has D119's already-decided six-month period. Privacy restoration remains MISSING and unchanged; live estimate methodology/labels and the target-area coverage rule still need approval.
- Binding criteria, selected PRD gate rows/mappings, privacy model and current preparation packs now reflect D108–D119. Historical package-close evidence and append-only decision rows remain unchanged; the stale Q11→Q31 cross-cutting note is in Part 2 and was updated. The PRD's explicit current amendment supersedes its older descriptions.
- The evaluator has five gates. The boolean phone-approval machinery and flag are gone, while current reference-based claims still fail closed. Money roles use one active admin; independent evidence, credential and release checks remain.
- The register retains 71 checklist identities and 22 PARENT rows. There is no promotion, new external value, new gate state or product behavior.

### A3 commands — PASS

| Command/check | Result |
| --- | --- |
| `python scripts/validate_progress.py` | Exit 0; canonical dependencies match frozen progress strings |
| `python scripts/validate_w403c_pilot_preparation.py` | Exit 0 |
| `python scripts/validate_w404a_training.py` | Exit 0 |
| `python scripts/validate_w404b_handover_preparation.py` | Exit 0; 7 files, 26 applicable external gates, 3 deferred validations |
| `python scripts/update_architecture_inventory.py --check` | Exit 0; generated inventory unchanged |
| `pytest -q tests/test_validate_progress.py tests/test_pilot_gate_evaluator.py tests/test_w403b_synthetic_runner.py tests/test_w403b_load_reproducibility.py tests/test_r59_real_stack_contract.py tests/test_validate_w403c_pilot_preparation.py tests/test_validate_w404a_training.py tests/test_validate_w404b_handover_preparation.py` | 120 distinct tests pass after the targeted correction/rerun below |

The initial batch passed 118 and failed two load unit cases because Git was unavailable in the container. Those tests now reuse the existing runner-test authority reader to evaluate this integrated source before the controller commits it. The real parser/evaluator and exact blockers still run; no policy result is stubbed and production remains HEAD-only. The entire corrected load file passed all 10 tests. The other 110 cases passed unchanged in the batch. The handover audit also exposed an obsolete `#safety-rules` runbook fragment; the link now points to the current manual runbook and its rerun passes. Test fixture copying excludes the prohibited account-access document.

Logs: external `req230-tools/part1-{progress,w403c,w404a,w404b-final,inventory,tests,load-final}.log`. `test_w403b_synthetic_path` (Playwright + database) is intentionally left to CI by the contract. The CLI's committed-authority check runs against the new HEAD after the controller commits; pre-commit tests explicitly use the reviewed source reader.

### A5 final integrated checks — PASS

| Command/check | Result |
| --- | --- |
| Exact `basedpyright` | Exit 0, zero unbaselined errors/warnings/notes |
| Baseline multiset subset audit | 286 → 207; 79 removed, zero added |
| `ruff check .` | Exit 0, including final test-fixture changes |
| Touched application tests | 56 distinct passes, as recorded under Part 2 |
| `python scripts/update_openapi_snapshot.py --check` | Exit 0; snapshot unchanged |
| `scripts/verify_preprod.sh --static-only` | Exit 0 on final tree; actual Compose renders and pinned-Caddy validation repeated |
| `git diff --check` | Pass |

Final logs/proofs: `part1-{types,ruff-final,openapi}.log`, `part2-static.log`, `final-baseline-proof.json`, `authority-audit.log`, `a1-allow-list.json`. All are under the external tools directory. Application types are the configured basedpyright scope; no type configuration was changed.

### A7 and handoff

Worker gates: combined privacy+money **PASS** and Part 2 security **PASS**, both `gpt-6.1-sol` / **high**. The controller's independent final minimal-change review remains required; this worker does not claim that review or full CI passed.

Second Docker hold: 19:33:43Z–19:38:40Z (about five minutes), one heavy process at a time. Windows Available memory was about 1.7–1.8 GB during checks and 1,888 MB at release. `cv-req230` remains stopped and retained as requested; its database is isolated. Own lock released, with no change to REQ-209's lock/container. No add, commit, stash, checkout, reset, push, deployment or business-provider call by the worker. HEAD remains `842e4c41`; the controller stages explicit paths and makes the two local commits.

## Final-review corrections and re-verification

The controller relayed Opus 5.5's **FIX** findings. Accepted Part 2 typing, baseline, casts, validation and fixture changes were not reopened. The six requested corrections are applied:

1. PRD G-12 and the handover legal row explicitly retain driver agreement/consent wording (Q26) and required disclosures, alongside the remaining legal obligations.
2. PRD G-15 again names the target-area coverage rule and coverage measure; ROI/attribution remain removed.
3. The existing `/admin/trip-checks` training row is restored with flags, holds, disputes and pass/fail spot checks plus a note, while forbidding automatic overdue-hold release and GPS-as-display-proof claims. The page exists and the training audit passes.
4. The historical PKG-05 plan activated on 24 August matches HEAD exactly. Its `EXT-AD-PLATFORM` reference is now the explicit A1 entry at `docs/delivery-contracts.md:703`; later historical line numbers are updated above.
5. Architecture G-advertiser explicitly includes `EXT-BASEMAP`, matching the unchanged evaluator and expected blockers.
6. Paystack's unrelated formatter reflow is reverted. Its source diff now contains only the accepted imports/session-factory type correction.

The controller re-froze progress after restoring agreement/consent wording. Its new SHA-256 is `8CDFB5ECE33D1440D00E21A6F8C57F7F46F0FDD31E98E27CFFF016130CE99ECA`; the requests hash remains `9E72F933016F5771053B3D1702E69A632B8DB4060B8D80B3A4AD5695DDD36246`. The worker re-hashed and audited these files without editing either.

Re-verification on the corrected tree:

| Check | Result |
| --- | --- |
| `python scripts/validate_progress.py` | Exit 0 |
| `python scripts/validate_w404a_training.py` | Exit 0 |
| `python scripts/validate_w404b_handover_preparation.py` | Exit 0 |
| `pytest -q tests/test_validate_progress.py tests/test_validate_w404a_training.py tests/test_validate_w404b_handover_preparation.py` | 71 passed |
| `ruff check .` | Exit 0, all checks passed |
| A1 grep/audit | Pass; 17 explicit allowed references |
| Authority/frozen-file audits | Pass; states, pinned evidence, 71 rows, 22 parents and pointers preserved |
| Historical plan comparison | Exact match with HEAD |
| `git diff --check` | Pass |

`ruff format --check app/services/paystack_disbursements.py` returns 1, as does the unmodified HEAD copy under the same repository configuration. Its only proposed change is the reflow explicitly reverted above. The controller confirmed that CI runs `ruff check .`, not `ruff format --check`: this is **pre-existing and not CI-gated**, so HEAD formatting is retained without ignores or configuration changes. Logs are external `req230-tools/review-fix-{format,head-format,format-diff,progress,w404a,w404b,tests,lint-all}.log`.

Correction Docker hold: 19:54:29Z–19:56:25Z (under two minutes). Available memory stayed above 800 MB and was 1,529 MB at release. The container is stopped and retained; own lock released. No Git-state changes. The controller forwards this corrected result to its final reviewer; that re-review is not claimed here.
