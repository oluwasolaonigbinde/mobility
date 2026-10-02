# L2-0 second dependency security repair

CI run 36918520508 on f172ab3 passed its backend shards, frontend checks/build, R59 and both real-stack end-to-end jobs, but the Python dependency audit failed on newly published PyJWT/urllib3 advisories. Changed-code coverage consequently did not run. REQ-054 remains in progress.

The owner approved dependency downloads only on 2026-10-02. Independent bounded-plan review passed before editing. No provider, account, deployment, commit or push action is included.

| Criterion | Verdict and evidence |
| --- | --- |
| Replace both affected versions | PASS: production input PyJWT 2.15.1; hash lock PyJWT 2.15.1 and urllib3 2.8.0. No advisory suppression or CI threshold change. |
| Primary release metadata and hashes | PASS: PyPI version metadata supplied both published distribution SHA256 hashes per version; downloaded wheels matched those hashes. Their selected versions had empty PyPI vulnerability arrays at verification time. This is not a claim that the full CI audit passed. |
| Preserve unrelated lock contents | PASS: normalize only the two target version/hash blocks and compare before/after byte text; every other entry and annotation is identical. The two blocks were refreshed directly from primary metadata without downloading compiler tooling. |
| Runtime/dependency compatibility | PASS: both releases support Python 3.12; no new required base dependencies for this runtime. Own isolated Python 3.12.14 verification container imported PyJWT 2.15.1 and urllib3 2.8.0. pip check: no broken requirements. |
| Authentication behavior | PASS: tests/test_auth.py, 47 passing cases including invalid/expired/malformed token rejection, refresh/session boundaries and password operations. Receipt ci-security-auth.xml outside Git. |
| urllib3 transport behavior | PASS: local ephemeral HTTP server in own verification container; actual PoolManager success/JSON response and 503 failure status, connection/read timeout configured, no external network request. |
| Independent final review | PASS: consolidated minimal-change and security/dependency specialist review independently checked exact diff, primary release metadata/hashes, compatibility and all criterion evidence; no actionable finding. |
| Full CI / D33 baseline refresh | Pending owner-authorized commit/push and passing full CI. coverage/baseline.json has not been changed from local evidence. |

Repeatable release inputs: https://pypi.org/pypi/PyJWT/2.15.1/json and https://pypi.org/pypi/urllib3/2.8.0/json. Detailed download/metadata receipts are retained outside Git in the isolated verification directory.
