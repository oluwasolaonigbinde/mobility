# W1B delivery contract — 5 October 2026

**Historical 5 October contract; the 6 October direction below supersedes its inbound-merge/per-lane CI gate.**

Authority: owner execution of `Cardvert_W1B_Budget_Hosting_Brief_2026-10-05.md`, REQ-037, REQ-049/D44 and REQ-108. Work only in `mobility-w1b`, branch `w1/budget-hosting`, from master `750edbb`. This is review-required money/deployment/security work. No external actions, provider calls, secret access, push, master merge or deployment; local commit is authorized by the brief. Requests remain IN PROGRESS until merged. Do not read account-access or tmp. No queue/status changes to progress.

## Outcome and scope

1. Quoted printing, installation, permits, design and other fixed lines consume the same governed campaign budget as media. Reuse the current billing authority: confirmed unreversed allocations before production, effective full VAT-inclusive accepted obligation after production, attributed to the production-start Lagos day for daily budgets. Both already include all line kinds; do not add fixed costs to amounts which already include them. Establish focused regressions, changing budget code only if they reveal an omission. Accepted quotation, invoice, payout and existing evaluation rows/key formats remain unchanged. Ratios remain approved configuration, blank/off in templates.
2. Replace deploy/render and deploy/aws files with Hetzner Object Storage CORS and a blank Hetzner configuration template referencing the existing standalone Compose/Caddy release topology. MapTiler uses the existing build-time MapLibre HTTPS style URL. Add only the required MapTiler API origin to connect/img CSP. No account, region, residency or key choice. Application bank/NIN key-ring custody remains unchanged; no KMS claim.
3. Add pinned-image ClamAV to private data plus outbound egress networks, with no published ports, persisted signatures, 4 GiB memory bound and service health/start dependencies for API/worker. Use the image's supported health probe, allow cold signature initialization, and set scanner host to its service name. Preserve fail-closed scanning. Make API WEB_CONCURRENCY explicit with default two, retaining configurable image behavior.
4. Integrate the new service with release preflight topology/image validation and its focused tests; otherwise the existing allowlist rejects the authorized Compose addition. This necessary caller update touches scripts/release_contract.py, not deployment authority or lifecycle. Document the historical 13 Batch F gap dispositions individually, retaining remaining operational/legal/provider gates. Correct superseded active staging instructions; historical research may remain labelled.

## Acceptance and verification

- A1: All named fixed lines plus an arbitrary other line count once at 80%, 95%, 100%; VAT and quantity remain canonical. Focused DB-backed flows cover confirmed funding and production obligation, total/daily dates, retry convergence, reversal/correction, immutable accepted prices and unchanged key examples. No payout inputs.
- A2: No obsolete deploy artifacts/references in current instructions; Hetzner CORS has exact origins and GET/POST, no public bucket/IAM/KMS assumptions; secrets blank and live switches/ratios unset. Parse templates and test configuration contract using ephemeral synthetic stand-ins only.
- A3: MapTiler HTTPS style passes unchanged to MapLibre; local schematic remains usable when unset; CSP permits api.maptiler.com fetches/sprites and keeps all other security boundaries. Focused frontend map tests plus static edge policy checks and a local HTTP-resource simulation if practical; no real provider fetch.
- A4: Compose config (no up/start) renders staging/production and release profile with healthy scanner dependencies, private port 3310, persistent signatures, egress, and two/configurable API workers. Release validator accepts valid topology and rejects missing/public/unsafe scanner or unpinned images. No stacks stopped or started.
- A5: Client topics/history, decisions (D61/D62 only if needed), Q rows where applicable, architecture v1.117 and placement/changelog, request statuses and deployment gaps accurately reflect the verified local result, without launch claims.
- A6: Touched checks pass; changed executable lines >=90% coverage and branches >=80%. Independent money, deployment and security reviews plus final minimal-change-review PASS, reporting actual models. Plan review precedes implementation. One reviewer at a time, read-only ownership, clean context. Claude owner review and full branch CI remain integration gates.

## Checkpoints and risk

Record requests first; inspect/review this plan; present any revised contract (scope already authorized); implement smallest complete change; verify each criterion; domain reviews; consolidated review and corrections until PASS; one local explicit-path commit with stable evidence. No migration is expected because existing immutable billing records already carry fixed lines. Use only touched test files; no full backend suite, coverage/type baseline or dependency edits. Existing main checkout and W1-P are hands off. Check Docker before any test container; CI has priority. Prefer the available Python environment and SQLite flows where applicable; explicitly disclose unavailable PostgreSQL/live evidence.

Main risks: double counting fixed lines; silently changing the preproduction spend basis; stale managed-release assumptions; scanner cold startup/signature download and resource fit; CSP overbroad origins; provider compatibility remains unexercised. No migration/backfill, payout, liability, legal residency decision, generic map abstraction, or provider credential work.

## Claude corrections — 5 October 2026

Owner review of `308f04a` requires the release path itself to allow cold scanner startup, with a regression test; plain budget current/history wording; at least 8 GB host RAM; and CI-green master integration with shared-test conflict resolution and next-free request/decision/architecture numbering (marked "renumbered at merge", after W1-P if it lands first). A4 now requires a 900-second application/scanner health wait, covering the 360-second scanner start period plus health retries, with unhealthy startup still failing before readiness/edge. A5 includes plain wording and the host minimum. Reverify touched files and return to the same post-build reviewer. No push authorization; integration remains blocked while master CI fails. Existing identifiers and correction request numbers are provisional until that merge.

W1B identifiers renumbered at merge on 2026-10-06: Compose REQ-108 → REQ-117 (REQ-115 is master preview rehosting), wording REQ-112 → REQ-116, D62 → D65, architecture v1.117 → v1.122. Master identifiers retain their meanings.

## Owner integration direction — 6 October 2026

Merge current local master (4cf1df66) with a real merge, preserve both lanes and master records, renumber W1B identifiers as above, rerun touched tests before the merge commit. Owner one-time D41 exception: no per-lane push/CI; one combined CI run later. Then wait for the payouts session to report its master merge; merge w1/payouts, resolve records conflicts, rerun touched checks and commit the combined Wave 1 branch. No push or merge into master. This supersedes the earlier CI-green/per-lane push gate for Wave 1 only.

## Owner master refresh — 7 October 2026

Real merge exact current master e502670 into combined Wave1, preserving incoming Next.js16.4.0/sharp0.35.5 package files and REQ-118. Preserve lane numbers and all records; reorder only D64/D65 rows, no decision-content changes. Rerun W1B touched files and review integrated source/evidence before committing. No push, deployment or merge into master; combined CI remains separately authorized later.
