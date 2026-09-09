# Delivery Control — Intended MVP, Delivered Work, and Ordered Queue

**Start here before every task.** This is the operational control document for
delivery: it shows the endpoint, what exists, the sole authorised package, and
the ordered remainder. Agents update it in the same change as every landed
package. The proposal owns scope, architecture owns design, decisions-log owns
product decisions, and Git/test evidence proves delivery; **this file alone
controls which package may be executed next**. It replaces the status-summary
role of `project-reconciliation.md` (4 Aug 2026) and the work-selection role
previously implied by `next-steps.md` (10 Aug 2026).

The endpoint is the D11 proposal scope **as superseded by the direct client
answers and approvals in D18–D20**, designed in `docs/architecture.md`.
Somto's Q1–Q34 list and the client's later three-point clarification are the
newest product authority. Architecture §31 is roadmap context;
execution order and authorization live exclusively in this document.

**Package:** one owner-facing delivery/review cycle. **Checklist item:** one of
the 71 original mandatory implementation obligations inside a package; it is
never an authorization unit. **Remediation slice:** one of the 60 owner-admitted
fix units in PKG-10; its immutable candidate and dependency mapping is the
authorization boundary. **Parent:** one of the 22 architecture traceability
groups; it is never executable. **Active slot:** the single package marked
`NEXT`, `IN PROGRESS`, or `REVIEW`.

## Execution lock

Package status is `QUEUED | NEXT | IN PROGRESS | REVIEW | DONE | BLOCKED`.
Checklist status is `TODO | DONE | BLOCKED — EXT-ID`; checklist items never use
package-active vocabulary. A package is `DONE` only when all its checklist items
are `DONE`. It is `BLOCKED` only when every non-DONE item is externally blocked
or transitively depends on blocked work and no runnable `TODO` remains.

The active package moves through `NEXT → IN PROGRESS → REVIEW → DONE`. Its
controller selects the current runnable checklist checkpoint, honors the
applicable dependency graph, and may use staged commits and parallel agents with
explicit disjoint ownership. PKG-10 slice state is `QUEUED | ACTIVE | COMPLETE`;
two dependency-ready, write-disjoint slices are the baseline; a larger current
capacity is valid only when the exact active slice set and disjoint-work
justification below are recorded before dispatch. Its displayed current
checkpoint is a controller pointer, not a claim that only one slice is ready.
A slice becomes `COMPLETE` only after its own plan review, diff review,
and named domain checkpoint have accepted evidence. Money, privacy, security,
client-device, deployment and other high-risk checkpoints receive specialist
review before integration; one consolidated independent package review closes
the owner-facing cycle.

**Current justified remediation writer capacity:** `2`
**Current capacity assignment:** ``
**Current capacity justification:** All 60 remediation slices are accepted and
the 86 FIX / 29 non-executable disposition reconciliation is closed. No further
remediation writer is authorized; the repository returns to its first unresolved
external checkpoint.

`Controller state` is `COMPLETE` only after all ten packages are `DONE`, all 71
original checklist items are `DONE`, and all 60 remediation slices are
`COMPLETE`. Retain `PKG-09` as the final control package and `PKG-09 / W4-04B`
as the terminal evidence pointer, as required by the repository execution
authority; PKG-10/R60 remains the remediation closure receipt. This is the only
valid zero-active state other than an explicit external pause.

At promotion, scan packages in order. A blocked earlier package does not freeze
the program: promote the first later package containing a runnable checklist
item whose transitive checklist dependencies are `DONE`. Never use invented or
placeholder external values. Only an owner-recorded decision clears a checklist
external block. If the active package has no runnable item, mark it `BLOCKED`,
report every blocking `EXT-ID`, and either promote a dependency-safe later
package or set the controller `PAUSED — EXT-ID` only when no runnable `TODO`
exists anywhere. A pause ID must be registered `MISSING` and must directly or
transitively block the pointed package/checkpoint.

External prerequisites distinguish build-entry inputs from live-use gates in
their “exact effect” text. Only an external ID named in a checklist item's
prerequisite cell blocks building that item; launch facts and legal approvals
that gate live use do not prevent provider-neutral or synthetic implementation.

### Current control pointer

**Controller state:** `PAUSED — EXT-PAYMENT-PROVIDER`
**Control package:** `PKG-03` — all provider-neutral commercial work is complete;
the remaining payment-provider checkpoint requires registered external authority.
**Current checkpoint:** `PKG-03 / W2-01C` — PKG-10 remediation is complete. R02 is accepted at `09c0b17`, R47 at
`419414a`, R03 at `60af07d`, R48 at `b17d1e7`, R05 at `954d9a4`, R49 at
`a315a59`, R33 at `14f155a`, R06 at `05b4901`, R07 at `84cb94e`, and R50 at
`bb8c13e`, R18 at `5c2d60a`, R19 at `3c7b678`, R51 at `2f52c3e`, and R31 at
`eb59a84`, R52 at `cab745c`, R20 at `d8cd891`, R21 at `ee43b10`, R22 at `7835ba8`, R55 at `662077a`, R57 at `2599b87`, corrected R58 at `0c1d525`, R59 at
`fcba0dc`, R17 at `c78b5dc`, and terminal R60 at `fc0cb3a`.
AUT-006 is accepted at
`a4c9de2`.
Every repository failure group
discovered by R02's complete 1,772-test authority run is now accepted: V11
historical migration fixtures, V12 signed-v2 payout fixtures, V13 reversal
deadlocks, V14 trip-end/enqueue lifecycle and the controller-state correction.
R54 is accepted. R39→R44 plus D30 are accepted as one integrated privacy/audit
chain with migrations 0075–0077. R29→R30 is accepted at `32d617f` and R45 at
`7f7bd1c`; R56 is accepted at `751060c`. R02's exact CI-authority patch now also
provisions the application Redis URL, `jq`, lockfile-pinned frontend dependencies and
Playwright Chromium; focused checks and an immutable frontend-image build are green.
Both Opus correction packets are accepted at `aa7ff02` and `bce94ad`, and R46
is accepted at `1c89f16`. R02's complete immutable run and focused complement are
preserved, but the focused W403B browser journey exposed a real trip-end protocol
failure now owned by R36→R37; R02 will resume only after that packet is accepted.
R36→R37 is accepted with migration 0080, signed mixed-batch disposition and
server-owned grace-expiry adjudication. R02's final W403B approval-aware correction
is accepted at `09c0b17`: the composed immutable authority is 2,541 passing
executions with zero skips, and R02-M, DB+DEP and R02-CP-CONTROL all pass. R47 is
accepted at `419414a` with complete caveated measurement facts, source/calibration
provenance, frozen ROI methodology and screen/CSV/PDF parity; R47-M and
R47-CP-REPORTING pass. Its released contract lane promoted R03 and its reporting
dependency promoted R48; both are accepted. R05 is accepted at `954d9a4`,
releasing the exclusive database lane to R06 while accepted R49 promotes R50 on
its disjoint report-reissue lease. The owner has now selected R17 Option A;
R17 planning is ready, while implementation waits for R59 to release the
central CI workflow lease.

## Direct owner requests outside the package queue

| Date | Item | Authority | Scope boundary | Queue effect |
| --- | --- | --- | --- | --- |
| 6 Sep 2026 | **Execute the reviewed post-remediation correction programme, C01–C37 and H07.** | Owner's exact `APPROVE IMPLEMENTATION OF THE REVIEWED PACKETS` in the existing Astra controller, following aggregate contract V3 plan-review PASS and the frozen two-macro-phase execution amendment | The existing Astra controller implements directly; no implementation subagents or initial handoff. Exactly two further Sol/medium review-only subagents: one complete Macro-Phase A review, then one fresh final specialist/consolidated review. This explicit owner amendment replaces intermediate specialist dispatches and earlier concurrency/model preferences for this programme only. No commit, push, merge, deployment or external-system contact is authorized. | Authorizes the bounded correction register below without changing the ten-package queue, original checklist, R01–R60 history or PKG-03 external pause. |
| 5 Sep 2026 | **Adopt R17 Option A: a changed-code coverage ratchet with at least 90% line and 80% branch coverage, plus no regression from exact current global and named-critical baselines.** | Direct project-owner choice “A” in the active remediation controller, 5 Sep 2026 | R17 must select its comparison base deterministically for PRs, pushes and local runs; fail closed to an explicit merge-base rule; exclude generated code, tests, fixtures, migrations, build output and vendor code. It may add only the minimum backend/frontend coverage tooling, policy tests, workflow wiring and a D27(e)-superseding decision row after an independent plan review. It must inventory and reuse existing tooling and must not duplicate R59's real-stack journey or evidence. | Clears the R17 policy block and authorizes read-only R17 planning now. Implementation remains serialized until R59 releases `.github/workflows/ci.yml`; R60 remains dependency-held until both R17 and R59 are accepted. |
| 4 Sep 2026 | **Require an explicit controller callback after every slice, and predeclare compatible multi-slice session lanes where they reduce repeated setup.** | Direct project-owner instruction in the active remediation controller, 4 Sep 2026 | Every controller-created task must call `send_message_to_thread` for controller task `01a05de2-0b5d-73f0-ae3d-0e979b734658` with its terminal receipt; ending only in the worker task is insufficient. One visible task may retain its original model and continue a predeclared dependency-ordered lane only when the slices share a domain, risk class and compatible ownership. It must return a separate receipt after each slice and wait for controller admission plus the next explicit packet. Cross-domain work, overlapping leases, migrations/generated contracts owned elsewhere, or a changed model require a fresh task. | Applies to all current and future controller dispatches. R07 and R50 remain standalone because their successors require different risk/model gates; R18→R19 and R20→R21→R22 are the first compatible reusable lanes. Missing callback delivery triggers one state reconciliation and adoption of existing work, never a duplicate implementation owner. |
| 4 Sep 2026 | **Use fresh visible sessions for new work; use GPT-5.6 Luna/max with fast mode for simple bounded tasks and reserve Sol for genuinely complex work.** | Direct project-owner instruction in the active remediation controller, 4 Sep 2026 | Do not use internal subagents as the execution owner for new slices. Before dispatch, apply the repository model gate to the task's actual hardest boundary: Luna/max fast is preferred for simple low-risk bounded work, Terra remains available for ordinary implementation, and Sol is used only for difficult money, security, migration, concurrency or cross-contract authority. Never reuse an older session under a changed model. | Applies to all future dispatches. Existing completed reconciliation workers are closed; R03 and R48 must begin in separate fresh visible sessions with proportional verification and terminal-only callbacks. |
| 4 Sep 2026 | **Use otherwise-idle disjoint capacity for the smallest verified controller-audit follow-up while the main remediation frontier is dependency-held.** | Direct project-owner instruction to maximize useful parallel execution, 4 Sep 2026; controller-selected FU-06 from the recovered row-385 audits | FU-06 may verify and, if current, correct mobile-width reachability of existing logout and change-password controls only. It owns the shell/account-control component and focused responsive tests; AUT-004 logout/session semantics, APIs, schemas, routes, generated contracts, R36/R37, R47 and user-owned design/theme work remain unchanged. | Adds one bounded side packet outside R01–R60 without moving the active PKG-10 pointer. Its exact disjoint lease and proportional verification must be recorded before dispatch. |
| 3 Sep 2026 | **Controller orchestration must not absorb or interfere with Claude tasks created independently by the owner.** | Direct project-owner correction in the active remediation controller, 3 Sep 2026 | Session reconciliation covers only tasks explicitly dispatched by this controller. Driver-journey, landing/design, future-delivery, external-dependency and other owner-created Claude work remain outside controller inspection, mutation, admission and scheduling authority unless the owner later places a specific result in scope. | Narrows the result-recovery task to the three controller-dispatched row-385 audits; the broader prepared Claude prompt was not sent. |
| 3 Sep 2026 | **Dispatch approved Claude Opus 5 High work immediately in fresh tasks; do not reuse old tasks or request a redundant model/send choice.** | Direct project-owner instruction in the active remediation controller, 3 Sep 2026 | The controller still applies the repository model gate, dependency graph, exact lease and no-duplicate checks before dispatch. Once a bounded Opus packet is approved by those controls, create a fresh Opus 5 High task and send it directly. Terminal-only callbacks remain required. | Applies to future Opus dispatches. It does not authorize dependency bypass, overlapping writes, or duplicate work. |
| 2 Sep 2026 | **Do not reuse an old task with a different model for new work.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | A visible task retains the model family selected when it was created. Related continuation may reuse it only without cross-model reassignment. When new work requires another model, create a fresh visible task with that model selected before dispatch, preserving cache efficiency and clear evidence provenance. | Applies to every future remediation and side-programme dispatch. The four V11–V14 correction packets were already created as new tasks directly on their chosen Terra/high or Sol/high models. |
| 2 Sep 2026 | **Launch the paused UI/product-review suite with 3–5 Claude Opus 5 High sessions as soon as the moving UI surfaces stabilize.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Trigger only after R11→R14 and R39→R44 are accepted and no overlapping auth, advertiser-planning, reporting, privacy-state, frontend, or generated-contract bytes remain unadmitted. The canonical programme is `issues/product-ui-review/README.md`; prompts 2, 3 and 5 are answered, while 1, 4, 6–8 and sequential 9–11 remain. They remain read-only and use terminal-only callbacks. | Durable side obligation; it does not interrupt or overlap the active remediation writers. Continue the remaining prompts in the canonical folder's documented order and reconcile every answer there. |
| 2 Sep 2026 | **Use terminal callbacks instead of routine progress narration.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Future sessions send one brief start acknowledgement, communicate only a genuine authority/scope blocker, and send one terminal completion callback. The controller does not poll or consume routine progress prose; admission remains based on the terminal receipt plus direct inspection of repository bytes, tests, reviews, and integration state. Current sessions were already instructed directly by the owner and are not messaged again. | Reduces token and attention overhead without weakening verification, callback responsibility, or controller admission. |
| 2 Sep 2026 | **Optimize remediation for parallel throughput and token efficiency.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Cohesive sessions continue across compatible slices without routine controller returns; focused checks run during development and expensive aggregates run once after bytes stabilize; valid reviews are reused; concrete findings and lease conflicts are consolidated; unrelated or environment-sensitive failures are attributed rather than allowed to create correction loops. Safety, required evidence, exact leases, and dependency serialization remain unchanged. | R02 must collect the complete failure set in one faithful aggregate rather than repeatedly stop at the first unrelated failure. The controller refills every released disjoint lane immediately but does not manufacture unsafe concurrency on the shared migration/generated-contract lane. |
| 2 Sep 2026 | **Apply a proportional verification budget to every remediation packet.** | Direct project-owner instruction in the active remediation controller, 2 Sep 2026 | Before dispatch, the controller assigns the smallest sufficient tier: test/fixture corrections run the exact regression plus affected module; ordinary product changes run red/green plus focused service/API and adjacent compatibility; money, authentication, migration or concurrency changes add only the relevant real-PostgreSQL/race/migration evidence; generated-contract changes add synchronization checks. A whole-repository or whole-frontend aggregate is prohibited per slice unless the packet itself is an approved integration checkpoint. One stabilized focused aggregate per cohesive packet is the default; unchanged accepted reviews and evidence are reused. | Broad suites are reserved for R02, R59, package closure, or an explicitly justified cross-package integration checkpoint. Unrelated failures are attributed once and repacketed; they do not trigger repeated broad reruns. The controller must reject or tighten any future dispatch whose verification scope exceeds this budget without a concrete risk-based reason. AUT-006 already complies and is not interrupted. |
| 2 Sep 2026 | **Vehicle approval uses an administrator-entered end date that may exceed document expiry.** | Direct project-owner/developer clarification in the active remediation controller, 2 Sep 2026; recorded as D31 | The driver supplies vehicle documents; an authorised Cardvert admin reviews them and selects the approval end date. No automatic earliest-document-expiry rule or 12-month cap applies. The chosen date and actor remain auditable, and expiry requires a new reviewed approval. | ONB-004 becomes eligible for current-source reviewed execution rather than remaining parked. |
| 2 Sep 2026 | **Reject duplicate driver NIN, normalized phone, or payout bank account; freeze planning-source links at terminal campaign states.** | Direct project-owner/developer answers in the active remediation controller, 2 Sep 2026; recorded as D30 | Duplicate checks must use protected/normalized authority without identity disclosure. Planning-source links remain editable for draft, pending, approved, scheduled, active, and paused campaigns; completed, cancelled, and rejected campaigns are read-only history. | ONB-003 and AUD-006 become eligible for current-source reviewed execution; neither is silently treated as already implemented. |
| 2 Sep 2026 | **Advertiser logins are single-company; one Cardvert admin may complete all driver approval checks.** | Direct project-owner/developer clarification in the active remediation controller, 2 Sep 2026; recorded as D29 | Advertiser membership permits exactly one active advertiser organization per login; Cardvert admins are unaffected. No maker-checker separation is added across bank verification, person/payee approval and vehicle approval, but existing immutable actor evidence remains mandatory. | AUT-007 becomes eligible for bounded enforcement after the central migration lane clears. ONB-005 requires current-source confirmation only and no manufactured implementation if existing audit authority already satisfies D29. |
| 2 Sep 2026 | **Driver activation uses administrator authorisation plus a driver-completed one-time setup link.** | Direct project-owner/developer clarification in the active remediation controller, 2 Sep 2026; recorded as D28 | Applies to the linked invited driver after person/payee and vehicle approval. The administrator never assigns the password; completion is single-use, rotates session authority and invalidates prior onboarding access. No live delivery provider is implied. | ONB-009 leaves the parked client-decision list and becomes eligible for current-source reviewed execution. |
| 2 Sep 2026 | **Adopt the recommended developer-policy answers** — privilege elevation reauthenticates and revokes globally; ambiguous End stops capture and retries identically; registration abuse uses scoped non-revealing limits plus alerts; bundled or managed PostgreSQL/Redis are allowed with production TLS/auth/host/secrets; coverage policy waits until runtime defects are finished. | Direct project-owner/developer response in the active remediation controller, 2 Sep 2026; recorded as D27 | Supplies behavior but no threshold, provider, hostname, secret, deployment or external evidence. Each formerly ambiguous candidate still requires current-source confirmation and a bounded reviewed implementation packet before code changes. | AUT-006, OFF-008, ONB-008 and REL-007 are eligible for execution planning rather than client blocking. R17/TST-007 remains deliberately parked. |
| 2 Sep 2026 | **Use Sol/medium for new remediation sessions by default** — reserve Sol/high or xhigh for an explicitly identified, unusually critical boundary rather than applying it automatically by domain label. Also surface developer-answerable decisions directly instead of parking them as if only the client could answer. | Direct project-owner/developer instruction in the active remediation controller, 2 Sep 2026 | Every future dispatch records its model and actual highest-risk justification. Sol/medium is the default; Terra remains suitable for ordinary bounded implementation/review and Luna for read-only inventory. A higher Sol reasoning level requires a concrete critical risk that medium cannot responsibly cover. Already-running sessions are not restarted solely for this policy change. Client/legal/external items remain parked, while developer-resolvable questions are presented to the owner in small decision batches. | Changes future dispatch/model selection only. Current safely running packets retain their existing models. The controller must solicit and record developer answers before treating those rows as blocked or parked indefinitely. |
| 2 Sep 2026 | **Separate buildable defects from client/external follow-ups** — park work that cannot be completed from repository authority in `to-do.md`, and keep the active remediation queue focused on product and engineering defects that can be fixed locally. Logout must revoke sessions on every device. | Direct project-owner/developer instruction in the active remediation controller, 2 Sep 2026 | Client/business/legal choices, unanswered later developer policy, external systems/evidence and trigger-dependent observations remain explicit and incomplete in `to-do.md`. R11 uses existing global `session_version` authority; R06 may apply the reviewed historical-downgrade safety exception; R28 derives admin activation from D18/Q15; R36 uses the reviewed durable migration/model/signing design. R17 is parked as undetermined CI coverage policy. | Unblocks R11, R06, R28 and R36 planning/execution without inventing client or external facts. Parked items do not consume implementation capacity or block independent engineering slices; all source IDs remain reconciled for final reporting. |
| 2 Sep 2026 | **Prefer cohesive multi-slice implementation sessions over one-slice handoffs** — pre-authorize each visible owner to continue through as many sequential slices as form one truthful bounded packet, rather than returning after every slice. | Direct project-owner amendment in controller task `01a05de2-0b5d-73f0-ae3d-0e979b734658`, 2 Sep 2026 | A packet may combine only dependency-aligned slices with compatible code surfaces, model gate, verification environment, specialist reviews and rollback/partial-completion semantics. Every slice/candidate ID, internal red/green checkpoint and separate admission receipt remains mandatory. Central migrations, generated contracts, shared fixtures, controller documents and overlapping services remain serialized. Packet size is evidence-derived, never an arbitrary target such as five. Owners proactively callback only when the full packet completes, blocks, conflicts or needs steering. | The rolling scheduler now prefers longer cohesive lane packets: current S09 may continue R26→R27 after a verified internal R26 checkpoint; future control, privacy, campaign, reporting and release sessions receive the longest safe dependency-aligned chain available. Controller admission still reconciles every slice exactly once at the packet terminal boundary. |
| 2 Sep 2026 | **R02 branch authority: every direct branch push runs CI** — retain the accepted GOV-003/R02 and architecture contract rather than narrowing it to master-plus-PR. | Direct owner choice in the active remediation controller, 2 Sep 2026 | R02 may additionally edit only `tests/test_validate_progress.py` to remove the stale master-only assertion and require every-branch push. The preserved three-path implementation, accepted plan/graph reviews and all other behavior remain unchanged. | Clears the R02 owner block and resumes its existing visible task; R03/R17 remain dependency-held until R02 admission. |
| 2 Sep 2026 | **Resume the approved Cardvert remediation programme from the exact safe pause snapshot** — preserve accepted commits and safely frozen work, avoid duplicated slices/reviews, and return to dependency-safe rolling dispatch. | Direct project-owner instruction relayed from controller task `01a001ce-d025-7531-a84c-7498cd819eda`, 2 Sep 2026 | Reactivates only the unchanged frozen R02, R09 and R35 packets first. R09/R35 may proceed through admission on existing valid receipts; R02 may resume only against its preserved exact lease and evidence. Later work retains the admitted R01–R60 graph, disjoint shared-checkout leases, the existing risk-based model gates, all 29 non-executable dispositions, and all external/live prohibitions. | Lifts `PAUSED — OWNER-SCOPE-RECONCILIATION`, sets the controller `ACTIVE`, and restores work-conserving refill after current frozen packets are reconciled. |
| 2 Sep 2026 | **Pause the admitted remediation programme for owner scope reconciliation** — preserve accepted commits and freeze every unfinished packet while the owner reassesses which of the 86 FIX candidates remain current product problems rather than CI/test/evidence/docs work or disproportionate hardening. | Direct project-owner instruction relayed from controller task `01a001ce-d025-7531-a84c-7498cd819eda`, 2 Sep 2026 | Preserve all accepted slices through R34 product commit `a95a7ca`; preserve the exact uncommitted R02, R09, R35 and unrelated user/audit bytes without staging, reverting, resetting, admitting or discarding them. No new R-slice, correction loop, review loop, writer, or lease may start. An already-running non-destructive R02 review may finish only to produce its frozen receipt. | Sets the controller to `PAUSED — OWNER-SCOPE-RECONCILIATION`, current writer capacity to zero, and awaits a narrowed approved inventory before any scheduler action resumes. |
| 1 Sep 2026 | **Use Claude Opus 5 High for the next two implementation sessions after the current set clears** — create the next two safely ready, mutually disjoint packets as visible Claude desktop Code sessions. | Direct project-owner amendment in controller task `01a05de2-0b5d-73f0-ae3d-0e979b734658`, 1 Sep 2026 | The controller must still select packets from the admitted graph, preserve exact slice/candidate IDs, dependencies, leases, stop conditions, review gates and shared-checkout safety. Sessions use saved Mobility `master`, direct checkout, no worktrees, Opus 5 / High. No external action or authority boundary expands. | Deferred trigger: after the currently active/reviewing R13, R24 and R34 set reaches safe admission/steering points, allocate the next two compatible ready implementation packets to Claude; do not displace current owners. |
| 1 Sep 2026 | **Execute the admitted Cardvert audit-remediation programme** — deliver the 86 FIX candidates through the dependency-safe R01–R60 graph with rolling, maximally useful parallel dispatch. | Direct project-owner authorization in task `01a05de2-0b5d-73f0-ae3d-0e979b734658`, continuing source task `01a001ce-d025-7531-a84c-7498cd819eda`, 1 Sep 2026; visible-task/concurrency and event-driven-callback amendments in the same controller task | Owns PKG-10, the exact admitted slice/candidate graph and repository fixes. Two implementation writers remain the baseline; a higher current capacity is authorized only with a recorded, exact disjoint-work justification. Implementation runs in visible top-level Mobility tasks directly in the saved checkout without worktrees, reusing a task across its compatible multi-slice session; internal subagents are review-only. Every visible task messages this controller only when its owned slice or planning packet completes, blocks, conflicts or requires steering; the controller then reconciles actual state before review, admission or refill. Periodic polling and recurring monitoring automation are disabled. Central configuration, migrations, contracts, shared fixtures and this file serialize. The 9 DEFER, 12 OWNER DECISION and 8 EXTERNAL INPUT findings remain non-executable; COM-008 remains open. No deployment, live payment/provider action, credential invention, external publication, legal approval, or live-evidence claim is authorized. The UI/product-flow prompt suite remains paused. | Activates PKG-10 and R01 first. After R01 acceptance, use the deterministic session partition and refill every safely justified writer slot without artificial batch boundaries. |
| 1 Sep 2026 | **Preventive minimal-structure and diff-review refinement** — prefer existing repository, standard-library, native-platform or installed capabilities before adding structure, and strengthen the existing post-build review for duplicated capability, unnecessary dependencies, self-justifying structure and low-value changed tests. | Direct project-owner request, 1 Sep 2026 | Owns one universal contribution-ready rule and the existing `minimal-change-review` mandate. It creates no new skill, review stage or repository gate and does not change VFD, OFD or DCD. | None. The completed controller state and terminal PKG-09/W4-04B pointer remain unchanged. |
| 1 Sep 2026 | **Durable deferred-obligation policy** — future package/checkpoint instructions must survive chat, agent and session boundaries as concise trigger/action/evidence-pointer reminders in the existing authoritative record. | Direct project-owner request, 1 Sep 2026 | Owns global instruction policy plus Mobility's root `AGENTS.md` mapping to this document and this control row. It creates no new planning document and adds no product code, API, data-model, workflow, architecture or decision change. | None. The completed controller state and terminal PKG-09/W4-04B pointer remain unchanged. |
| 1 Sep 2026 | **Independent-audit corpus and remediation programme** — preserve the completed GPT-5.6 Pro, Claude Opus and Codex audit responses in-repository; inventory omissions; reconcile, deduplicate and evidence-check their findings; produce a dependency-safe remediation order before any fix work; and preserve the later UI/product-design prompt suite for a separate pass. | Direct project-owner request, 1 Sep 2026 | Owns `issues/**` and `.codex/delivery/cardvert-audit-reconciliation/**` for collection and planning. Raw audit responses remain provenance artifacts rather than product authority. Any later product-code correction requires a finding-specific reviewed contract, current-source verification and the normal contribution-ready gate. External/live inputs remain external; this request does not mark them present. | None. The completed build-controller state and terminal PKG-09/W4-04B pointer remain unchanged. |
| 1 Sep 2026 | **Final Cardvert/Terrax Media identity sweep** — remove every tracked reference to the superseded working name and use Cardvert for the product/app and Terrax Media for the business. | Direct project-owner request, 1 Sep 2026 | Owns repository branding copy, comments, tests, documentation, the auth timing-equalizer sentinel, the saved-theme key and the offline queue database name. The two local persistence names are intentional pre-distribution clean breaks: no legacy fallback is retained and IndexedDB schema/version behavior is unchanged. Git history, dependencies and external services are excluded. | None. The completed controller state and terminal evidence pointer remain unchanged. |
| 28 Aug 2026 | **Repository instruction normalization** — make root and nested `AGENTS.md` the only active repository instruction sources and remove the legacy lowercase `agent.md`. | Direct project-owner request, 28 Aug 2026 | Owns repository instruction wiring only: root `AGENTS.md`, `CLAUDE.md`, and removal of `agent.md`. Historical `docs/build-loop/**` evidence remains unchanged. Adds no product code, API, data-model, workflow, architecture, or decision change. | None. The completed controller state and terminal evidence pointer remain unchanged. |
| 25 Aug 2026 | **Terrax Media public landing page** at `/landing` — brand-grounded marketing page for the OOH vehicle-advertising product, built from `docs/brand/terrax-media/` and the D18 Q1–Q34 confirmed answers. | Direct project-owner request, 25 Aug 2026 | Owns only `frontend/src/app/landing/**` and `frontend/public/brand/terrax/**`. It does not alter API, data-model, business-logic or package authority. | None. The public marketing surface is outside the 71-item MVP checklist. |
| 25–26 Aug 2026 | **Visual directions 7–9** for the demo/pitch theme system. **7 “Terra Grain”** and **8 “Coverage”** are grounded in `docs/brand/terrax-media/`; **9 “Broadside”** is adapted from the owner-supplied Terrax landing page. | Direct project-owner request, 25–26 Aug 2026 | Owns the shared direction surface: `frontend/src/app/globals.css`, `frontend/src/lib/themes.ts`, `frontend/src/lib/fonts.ts`, `frontend/src/app/layout.tsx`, `frontend/src/lib/map/config.ts`, `frontend/public/themes/**`, theme tests and `docs/design/**`. Adds no API, data-model, business-logic or workflow change. | None. The switchable design directions are a demo/pitch affordance outside the 71-item MVP checklist. |

### Approved post-remediation correction register

**Correction authority:** aggregate contract V3, source-validated and independently
reviewed by Sol/high in this controller task; exact implementation approval on
6 Sep 2026. The owner then froze direct Astra implementation and two Sol/medium
implementation reviews. This register is the executable direct-owner exception;
historical audit files and chats create no additional scope.

**Entry state:** HEAD and local `origin/feat/post-remediation-audit-baseline` both
`00918531b2bb37a1d184d1d4f917f659b9e4d80b`; branch `master`; no tracked/staged
changes. Preserve the four files in the pre-existing untracked
`.codex/delivery/cardvert-audit-reconciliation/`, the four `cardvert-*-38094d6.zip`
archives and `tests/test_audit_route_coverage.py.orig`. All nine initial hashes
were rechecked unchanged before approval. Never reset or substitute the baseline.

**Implementation owner:** this existing Astra session, exclusively. Migrations,
generated contracts and shared files are serialized. No implementation subagents
or simultaneous Astra owners. Current correction work: **Local A+B implementation accepted; execution/external gates remain open**.

| Macro phase | Dependency-ordered packet TODOs | Acceptance/review trigger |
| --- | --- | --- |
| A — DONE (local acceptance; external gates retained) | P01 C09; P02 C36; P03 C10/C11/C13/C16/C18; P04 C01/C02/C03/C07/C08/C12/C14/C15/C17; P05 C04/C05; P09 C35/H07; P10 C34/C37 | Sole Sol/medium review PASS after bounded browser and coverage resolution, 8 Sep. C34 remains an external gate; the six standard-image cases subsequently passed under the bounded owner amendment below. This is not release/deployment acceptance. |
| B — DONE (local acceptance) | P06 C06/C19/C20/C21/C22/C23; P07 C24/C25/C26/C27/C28; P08 C29/C30/C31/C32/C33 | Corrected final Sol/medium review PASS received. Existing Astra implemented and verified P06, then P07, then P08 directly, without implementation agents or handoff. Integrated evidence and external/execution gates are retained below. |
| Integrated closure — LOCAL PASS / GATES OPEN | All C IDs and H07 reconciled; contracts, recovery-head validation and integrated evidence reviewed | The one reserved fresh Sol/medium reviewer returned corrected PASS/no findings over both phases, full diff, red/green, deterministic/browser/local-stack evidence and exact external gates. No third implementation review dispatch; release/deployment closure remains blocked by those gates. |

P02 establishes controlled refresh tooling first; actual coverage baselines move
only against stabilized measured evidence without weakening D32. Every public
shape change synchronizes `openapi.json`, `docs/api/openapi.snapshot.json` and
`frontend/src/lib/api/schema.d.ts` immediately and reruns R14-B fixtures. New
schema changes are additive after 0084 in one linear chain; only the specifically
approved 0077/0082 downgrade guards may amend historical migration code.

**Accepted decisions and limits:** C15 retains minimal disclosure protection
indefinitely and removes TTL deletion because no governed source-retirement
authority exists; live legal approval stays closed. C17 preserves open/completed
history, hides blocked open tasks from actionable work and rejects completion.
C22/C23 use signed economic ledger facts and terminal-period membership for new
versioned runs, following `docs/measurement-methodology.json`; historical
calculations/manifests/issued reports remain immutable. C31 recovers only failed
or remaining creative work on the existing campaign under existing edit limits.
C34's incapable historical predecessor remains ineligible: implement the signed
capability and negatives, but no usable rollback or positive accepted-image
rehearsal claim until a genuinely compatible accepted predecessor exists.

**Admission rule:** each material behavioral test needs observed baseline red or
the smallest safe isolated mutation, then green. After each packet run focused
deterministic tests, inspect scope, record evidence/risks and update each owned
ID independently. Use real PostgreSQL for lock/race/serialization/migration and
money authority; local MinIO/S3 faults for promotion/deletion/delayed writes and
versions; real browsers for hostile same-site origins, End/visibility/IndexedDB,
partial acknowledgements and ordinary user journeys. Do not claim skipped jobs,
compiled code or a focused green check as aggregate proof. Preserve immutable
review/audit/financial/report history, D27 security, accepted payout terms,
screen-on PWA behavior and local evidence. No CASCADE, wildcard origins/CSP,
untracked provider attempts, blanket database-ahead readiness or weaker tests.

| Canonical ID | Disposition | Required behavior / evidence target |
| --- | --- | --- |
| C01 | VALID / IMPLEMENTED | Both KYC submission shells survive immutable decisions; one-way complete payload purge and reference fence commit before provider deletion. Preserve shared files; test restrictive FKs, concurrent binding and every crash boundary. |
| C02 | VALID / IMPLEMENTED | Exact orphan evidence reconstructs trustworthy bounds; current horizon rechecked before DDL; ambiguous recovery blocks destruction. |
| C03 | VALID / IMPLEMENTED | Confirmation adopts only exact matching promoted destination after rollback/lost response; source not deleted before durable authority. Local PostgreSQL/MinIO fault evidence below; live-provider gates remain. |
| C04 | VALID / IMPLEMENTED | Every issued write including transport retries must resolve; every version/delete marker adjudicated before CLEANED. Unknown outcomes stay nonterminal and visible. |
| C05 | VALID / IMPLEMENTED | Fresh User → Organization → Campaign → Membership locks precede ReportIssuance → PublicationIntent; real PostgreSQL request/completion inversion regression. |
| C06 | VALID / IMPLEMENTED | Due ordering includes durable worker-failure audit time, so a full failed prefix rotates without changing intent state or fabricating provider attempts. PostgreSQL/SQLite red-green plus preserved claim/finality races pass; evidence below. |
| C07 | VALID / IMPLEMENTED | 0077/0082 downgrade population checks and DDL serialize writers; populated deletion authority and unsafe publication states fail closed. |
| C08 | VALID / IMPLEMENTED | Calendar subtraction clamps short months while preserving UTC time; all retention surfaces share the correct cutoff. |
| C09 | VALID / IMPLEMENTED | Only the R59 contract test's import ordering changes; focused Ruff red/green, no skipped-CI implication. |
| C10 | VALID / IMPLEMENTED | Administrator creation requires D27 active actor/current-password/session proof and fail-closed limiter. |
| C11 | VALID / IMPLEMENTED | Invited admins cannot exercise admin authority/self-activate; all effective admin grants get reauthentication and correct global target revocation. |
| C12 | VALID / IMPLEMENTED | Collection authority before protected intent and again before confirmation/exact retry and protected vehicle evidence binding. Protected driver/applicant routes and binding regressions pass. |
| C13 | VALID / IMPLEMENTED | Locked report authorization refreshes stale ORM user/org/campaign/membership state; PostgreSQL revocation race. |
| C14 | VALID / IMPLEMENTED | Append-only typed actor/subject resolutions survive target/user deletion without users FK; distinct event counts and exact assignment/proof ownership exclude unrelated subjects. Migration 0086 preserves audit bytes and explicitly records unresolved targets/unrecorded actors. |
| C15 | VALID / IMPLEMENTED | Minimal disclosure history survives old TTL and delayed differencing; migration 0085 backfills absent expiry, blocks lossy downgrade; no invented retirement authority or live approval. |
| C16 | VALID / IMPLEMENTED | Shared unsafe BFF Origin/Fetch Metadata/media boundary before parsing/relay; full route inventory plus hostile same-site browser proof. |
| C17 | VALID / IMPLEMENTED | Purpose-matched active consent/current contact checked at creation, exact retry, actionable listing and completion; PostgreSQL withdrawal races preserve history and OPEN/COMPLETED states. |
| C18 | VALID / IMPLEMENTED | Exact configured storage origin in production CSP; real approved/hostile upload-origin checks; no wildcards. |
| C19 | VALID / IMPLEMENTED | New group members, signature changes and insufficient evidence retain existing unresolved replay flags and their money holds. Only governed review resolves them; 78 fraud/replay/earnings checks pass. |
| C20 | VALID / IMPLEMENTED | Earlier ended/unsealed payable predecessors block later cap allocation until chronological processing; shared-day and midnight conservation. |
| C21 | VALID / IMPLEMENTED | Frozen accepted start and end both govern admission despite mutable campaign edits. |
| C22 | VALID / IMPLEMENTED | New versioned reports freeze nonvoided signed ledger economics and coherent cutoff; no debt/settlement double count or missing-ledger fallback. |
| C23 | VALID / IMPLEMENTED | New denominator uses ended_at in the half-open period; active-at-boundary separately disclosed; no missing/double-counted cross-period trips. |
| C24 | VALID / IMPLEMENTED | Durable identical End request; current-trip flush precedes reconciliation across same-page/reload lost responses. |
| C25 | VALID / IMPLEMENTED | One End generation fences every asynchronous watcher/resume/write/manifest/flush/release boundary; no capture after End is sent. |
| C26 | VALID / IMPLEMENTED | Cancellation remains a distinct terminal historical capture cutoff, including quarantine adjudication. |
| C27 | VALID / IMPLEMENTED | Heading [0,360), optional invalid sensor readings normalized before immutable queue/hash; valid peers and old retained evidence preserved. |
| C28 | VALID / IMPLEMENTED | Atomic encrypted signed receipt/dispositions; accepted/rejected/settled counts truthful across reload; no settled-batch resend. |
| C29 | VALID / IMPLEMENTED | Upload cache binds exact selected file/purpose/access context; replacement and stale async completion cannot reuse wrong IDs. |
| C30 | VALID / IMPLEMENTED | Application convergence from both approval orders and exact retries with one audit/decision outcome; D28 activation stays separate. |
| C31 | VALID / IMPLEMENTED | Recover failed creative attachment on already-created campaign across retry/reload without duplicates or edit-authority bypass. |
| C32 | VALID / IMPLEMENTED | Ordinary idempotent demo seed establishes real production Start authority; normal persona completes the trip flow without R59-only repairs. |
| C33 | VALID / IMPLEMENTED | Per-item unexpected email failures isolated, observable and durably recoverable with fair traversal. Expired uncertain claims recover above handled attempt cap using stable provider key. |
| C34 | EXTERNAL VERIFICATION REQUIRED | Local signed qualification/accepted-recovery capability and negative tests implemented; ordinary exact-schema/worker readiness preserved. Accepted capable predecessor and positive distinct-image forward-schema rehearsal unavailable. |
| C35 | VALID / IMPLEMENTED | Runtime 422 envelope, OpenAPI/snapshot/TypeScript agree; rejected inputs stay private; R14-B fixtures rerun. |
| C36 | VALID / IMPLEMENTED | Controlled trusted-ancestor inventory/policy refresh supports add/rename/delete without reducing D32 floors or accepting missing evidence. |
| C37 | VALID / IMPLEMENTED | Both image heads and signed predecessor identity derived/validated; final DB head exact; stale/multiple heads rejected. |
| H07 | Documentation correction implemented | Architecture §6.5 authentication limiter wording becomes fail-closed; runtime unchanged. |

**Audit accounting:** 37 canonical corrections + six duplicate entries + H07 =
44. Security X-01 maps to C18/H02; Security X-02, Money PA-X01, Workflow F11 and
Horizontal H01 map to C09; Money PA-M06 maps to C04. No duplicate implementation.

**Evidence at admission:** exact refs/worktree and nine untracked hashes PASS;
`scripts/validate_progress.py` PASS; tracked/staged diff checks PASS; focused
`ruff check --no-cache tests/test_r59_real_stack_contract.py` FAIL, one I001.
Both OpenAPI artifacts advertise 239 HTTPValidationError validation responses.
No behavioral suite, migration, browser, provider or recovery rehearsal ran in
planning. V3 independent review PASS resolved six findings: both KYC payloads,
all storage attempts/versions, durable actor/subject links, no invented disclosure
retirement, incapable predecessor gate, and both authoritative image heads.

**Packet evidence (uncommitted working tree, not exact-SHA CI):**

- P01/C09: baseline Ruff I001 observed; the single blank-line correction passes
  focused Ruff and all seven `tests/test_r59_real_stack_contract.py` tests.
- P02/C36: 28 coverage-policy tests plus the seven R59 contract tests pass
  (35 total). Twelve initial refresh tests failed against the missing baseline
  capability; the CI-wiring regression also failed against the bootstrap-only
  workflow. Deliberately disabling ratio/inventory/receipt/instrumentation guards
  produced 11 expected failures; disabling ancestry/eligibility guards produced
  two expected failures. Both temporary mutations were restored before the
  final 35-pass run. Tests use isolated temporary Git repositories; no Mobility
  commit was created. Actual `coverage/baseline.json` is unchanged and its final
  refresh remains an integrated evidence obligation. No remote CI run is claimed.
- P03 in progress: ten new administrator API cases failed before the grant
  correction; all 25 administrator tests now pass. Five real-PostgreSQL stale
  report-scope cases failed before fresh locked reads and pass afterward.
  Administrator frontend tests demonstrated four failures before the password
  flow and now pass five cases. The shared BFF boundary demonstrated 15 denial
  failures before correction; all 21 boundary/proxy cases now pass. All three
  public contract artifacts are synchronized; 115 preserved PWA/session/queue/
  tracker fixtures pass and TypeScript passes. The combined authentication-race
  and report run returned 62 passes, five report failures, no skips. Those five
  reach the renderer with SQLite's timezone-less issuance timestamp; an
  in-memory baseline authorization substitution reproduced the same failure.
  P05 must resolve the test-environment mismatch and demonstrate publication on
  real PostgreSQL before accepting its integrated evidence. No renderer checks
  or immutable report timestamps may be weakened to bypass this failure.

- P03 accepted for local packet progression: four additional PostgreSQL
  creation/activation versus actor-revocation interleavings pass; bypassing the
  session-version comparison in memory made both containment-first cases fail,
  and the restored run passes all four. Eight live Caddy/browser checks pass;
  the three positive exact-origin cases failed under the baseline CSP, and the
  browser upload test also failed under an in-memory baseline Caddy substitution.
  The configured origin receives one synthetic multipart upload; the other
  origin receives none. A running Next/Chromium same-host, different-port
  hostile-origin POST returns 403 with zero backend calls; the same-origin
  bodyless POST returns 200 with exactly one backend call. This exposed Next's
  empty body stream, now covered by byte-based empty/nonempty stream tests.
  All 28 focused frontend tests, TypeScript, scoped ESLint/Ruff, contract
  regeneration check, progress validation and diff whitespace checks pass.
  OpenAPI/deployed-boundary/release-preparation tests pass 462 cases. P03 diff
  reviewed for scope. Provider MinIO/IAM/versioning/CORS verification remains
  part of integrated storage evidence; no live-provider or deployment claim.

- P04/C08: five short-month/timezone cases failed before correction; all seven
  calendar-cutoff cases now pass. C02: five migrated PostgreSQL orphan-recovery
  tests failed before correction; the 26-case lifecycle suite passes, followed
  by 12 affected detach/recovery cases after moving the global refusal gate
  ahead of all destruction. Recovered receipts retain exact reconstructed
  bounds; incomplete/conflicting/unclaimed/currently retained orphans stop the
  run, and current settings are rechecked at the drop boundary. C07: all three
  populated 0077 states and both check-to-DDL writer races failed before guards;
  all 13 guard/0077/0082 migration tests now pass, including empty down/up and
  schema drift checks. NOWAIT locks include authority, FK parents and fenced
  reference tables so busy cross-table writers make downgrade fail closed.
  Focused Ruff passes; these are isolated local databases, not live retention.

- P04/C03/C12: the upload/KYC/person-payee/vehicle/installation suite passes
  68 tests. Baseline failures cover four protected intent cases, four protected
  confirmation cases, two vehicle binding cases, two S3 source-preservation
  cases and two PostgreSQL confirmation rollbacks. Removing the collection gate
  in memory makes both applicant confirmation/retry tests return 201 instead of
  the required privacy denial; restored tests pass. Two actual local MinIO
  copy-response-loss/database-rollback recoveries pass, including source expiry
  simulation. Disabling destination adoption in memory makes both fail and
  three adopted-object metadata tests return the wrong disposition; restored
  tests pass. Temporary objects remain under the existing unconfirmed lifecycle;
  no production lifecycle/IAM/provider authority is asserted.
  A broader driver-approval run exposed two frozen-binding fixture failures
  before the intended eligibility assertions. Baseline-source reproduction and
  fixture correction remain integrated-verification obligations; do not weaken
  production trip admission. The initial applicant test configuration omitted
  registration enablement; it was corrected before recording useful red/green.

- P04/C15: all three delayed-query/scheduled-retention cases failed on the old
  TTL behavior. All 32 disclosure/composition/0045/0085 checks pass with real
  PostgreSQL enabled and no skips. Omitting 0085's expiry backfill in memory
  fails the migration preservation assertion; restored migration passes. The
  migration retains every other history field and refuses populated downgrade.
  Live legal approval remains absent; no source-retirement authority is invented.
- P04/C17: ten of twelve withdrawn, purpose-mismatched and superseded-phone
  cases failed against baseline. The 22-case contacts/notifications suite now
  passes, including both PostgreSQL completion/withdrawal orders. Restoring the
  baseline contact functions in memory demonstrates premature completion while
  withdrawal holds authority; the corrected path waits and then denies. Tasks
  remain OPEN when blocked, completed evidence stays visible/replayable, and
  neither consent nor task history is deleted. Focused Ruff passes.
  Both broader driver-approval fixture failures were reproduced with all `app`
  Python modules loaded from exact baseline Git blobs in memory; they remain
  local integrated-verification obligations rather than corrected behavior.

- P04/C14: target-aware DSR count was zero on baseline instead of the two
  subject-targeted case events. Corrected inventory counts actor/target overlap
  once and excludes foreign-subject events. The 86-case audit/migration/DSR/
  contacts/payee aggregate passes with real PostgreSQL enabled and no skips;
  the separate owned 0085/0086 schema comparison also passes. Atomic attribution
  survives profile/actor deletion and rolls back with its event. Compound
  measurement/report links use proof-bound subjects; campaign events use only
  the exact matching assignment. Payee, bank account, batch/line/intent and
  correction-trip ownership are exercised without provider execution.
  Restoring actor-only resolution in memory fails all 34 missing-target cases
  plus atomic attribution; separate corrected-fixture runs fail compound
  proof, money and frozen-migration attribution assertions. Removing backfill
  source locks lets concurrent profile deletion cross the migration boundary;
  restored migration serializes it and retains attribution. The migration
  leaves audit bytes unchanged, refuses populated downgrade, and rejects
  resolution update/delete/truncate. It never guesses unresolved historical
  identities. These gaps remain explicit operator/legal evidence obligations.
  The new subject-aware self-audit count exposed assessment-retry drift; exact
  system-count retries now preserve accepted counts while current absence/
  erasure checks remain. A changed external-count test caught over-broad retry
  handling (201); the narrowed system-only handling returns the required 409.
  Public response schemas are unchanged; no new privacy response wording or
  live DSR approval is claimed. Next P04 work is C01's durable KYC purge shells.

**Deferred closure obligations:** after A review PASS assess session health before
B; after all bytes stabilize complete the one fresh final review and reconcile
all IDs. Actual provider IAM/CORS/versioning, legal/privacy/report methodology,
physical-device GPS/battery, accepted recovery images, staging/production and
pilot evidence remain open when unavailable. Exact-new-SHA CI requires separately
authorized commit/external CI: never attribute uncommitted corrections to HEAD.
Final report must identify SHA/worktree, individual dispositions/H07, actual
red/green and integrated evidence, reviews, risks, and distinct behavioral-clean,
release-ready and deployment-ready verdicts. No completion by association.

- **P04 / C01 — locally demonstrated:** migration 0087 retains both submission
  identities and restrictive immutable-review links. Complete NIN/vehicle-payload
  clearing, document detachment, audit authorization and object-deletion receipts
  commit before provider calls. One-way database guards reject partial/unaudited
  retirement, restoration, identity changes and new document bindings. ORM and SQL
  writers take the parent before the file; legacy unretired deletion owners stay
  blocked while current-policy retirement supplies authority. Shared files survive;
  payload consumers return 410 and sanitized reads expose null payloads/purge time.
  Five migrated tests cover both decision chains, failed commit, reveal/rewrap,
  document-binding serialization, empty/live-payload upgrade/downgrade, populated
  refusal and writer locking; focused retention/KYC/person-payee/OpenAPI aggregate
  **41 passed**, including the nine updated lifecycle invariants. The baseline
  driver/vehicle boundary tests were red before implementation. In-memory removal
  of the 0087 guards makes both unauthorized-clear cases fail, and removing ORM
  parent-first locking makes the real race fail on the held file row; restored
  tests pass. Actual local MinIO delete-then-lost-reply recovery passes: all three
  receipts complete, the retired payload stays absent, and three peer objects
  survive. Restoring both baseline deletion entry points in memory makes this
  MinIO test fail because the payload was not durably retired; restored test passes.
  All three generated contracts are synchronized; 115 preserved queue/session/PWA/
  tracker fixtures, TypeScript and scoped Ruff pass. Architecture §19.4 and the
  incident runbook now describe durable cleanup rather than rollback resurrection.
  Inspected the C01 diff; no review/financial/audit history is cascaded away. Live
  retention authorization and production storage/versioning/IAM/CORS remain open
  external gates. The two pre-existing frozen-binding fixture failures remain an
  integrated obligation. P04 is locally demonstrated; next is P05 C04/C05.

- **P05 / C04, C05 — locally demonstrated:** request and publication completion
  use User → Organization → Campaign → Membership → Issuance → Intent order;
  immutable measurement runs no longer take an overlapping row lock. The real
  PostgreSQL scope-versus-publication test fails before the change because the
  publisher owns the issuance while waiting for scope, and passes afterward.
  Migration 0088 adds per-call registered/settled/uncertain write receipts and a
  required default-free generation protocol marker. Registration and retirement
  serialize on the intent; cleanup skips unresolved calls before its batch limit;
  both settled calls are required for publication. The S3 generated-write client
  issues exactly one SDK request and distinguishes uncertain transport failure.
  Cleanup deletes/verifies every exact-key version and marker, preserving peers.
  Existing non-complete generation history, including old cleaned claims, stays
  unchanged apart from an explicit legacy protocol classification and linked
  unknown-write evidence. Old publishers cannot create new untracked generations.
  No timeout, empty read or later successful generation establishes settlement.
  Unresolved legacy/provider calls require external evidence and a separately
  reviewed reconciliation procedure; no receipt rewrite or invented proof exists.
  CSV/PDF delayed-call tests were red (cleanup returned 1 prematurely), then pass.
  Falsely settling uncertainty makes both the service and real-MinIO late-write
  tests fail; omitting migration backfill fails all five affected legacy states;
  disabling receipt guards or adding an unsafe marker default fails their tests.
  Restoring SDK retries makes a local HTTP fault server observe five PUTs instead
  of one; restoring ordinary delete leaves versioned MinIO bytes/markers behind.
  All mutations were process-local; the owned fault-test bucket was cleaned.
  Final report/storage/OpenAPI/inventory aggregate **82 passed**, including nine
  real-MinIO cases; final 0088/0082/0077 downgrade/serialization aggregate **17
  passed**. Earlier report/renderer/migration/inventory aggregate passed 61.
  The five inherited SQLite report failures are resolved without weakening the
  renderer: UTC database timestamps are serialized with their zone when freezing
  new snapshots/render metadata. Two previously unreachable PDF test assertions
  now decode the embedded Unicode map and retain every disclosure/hash assertion
  across layout wrapping. Published/frozen historical bytes are not rewritten.
  Scoped Ruff and diff whitespace checks pass; inspected P05 source/migration/test
  diff. Architecture §27 and the operations runbook describe settlement, lock
  order and unknown/legacy gates. P09 C35/H07 is next; Macro A review remains
  reserved until all A packets and integrated verification stabilize.

- **P09 / C35, H07 — locally demonstrated:** FastAPI's shared 422 response now
  uses the project's `ErrorResponse`/`ErrorDetail` schema. Existing exception
  handlers, codes, messages, details and input redaction are unchanged. Both new
  contract tests failed against the prior HTTPValidationError contract and now
  pass, including actual path/query/body validation and request-ID preservation.
  OpenAPI, snapshot and generated TypeScript are synchronized; backend error/
  OpenAPI suite **25 passed**, all 115 preserved queue/session/PWA/tracker fixtures
  pass, TypeScript passes, and scoped Ruff plus byte-stability checks pass. One
  initial command named a nonexistent contract-test file and collected no tests;
  the corrected command produced the reported 25-pass result. Architecture §9
  documents the common envelope. H07 changes only §6.5's obsolete limiter wording
  to D27/R12 fail-closed behavior; queue-loss recovery remains unchanged. Inspected
  the contract/documentation diff. P10 C34/C37 is next; accepted distinct-image
  recovery evidence remains explicitly external, never supplied by a modified
  copy of the historical previous image.

**P10 local evidence (C34/C37):** 521 readiness/release/authority tests pass,
including real PostgreSQL exact-forward/multiple-row rejection, public-readiness
isolation with a signed token present, and actual isolated Compose/container
preservation of signed values containing dollar characters. Baseline unsigned
`--allow-database-ahead` accepted authority (red); it is now rejected. In-memory
signature bypass produces five red cases; bypassing recovery worker checks one;
restoring the baseline incomplete qualification validator six; removing the
recovery health override one; skipping exact image-label validation one; using
the baseline rehearsal's obsolete head one. All restored checks pass. The real
historical-predecessor script negative exits before any build/infrastructure
command; no application or packaging code is copied into the predecessor.
Version 3 receipts and separate qualification/recovery scopes replace the broken
public-readiness recovery assumption. Full Ruff, shell syntax, progress validator
and whitespace checks pass. Source/configuration/doc diff inspected. C34 remains
`EXTERNAL VERIFICATION REQUIRED`: no accepted capable predecessor, signed positive
two-image rehearsal or deployment evidence is claimed. Next: finish aggregate
Macro-A verification and inspect its complete diff before the sole Macro-A review.


**Macro-A integration in progress, 7 Sep 2026:**

- KYC retirement now uses the shared exact-key all-version deletion capability.
  Actual versioned MinIO reproduced the old error: completed deletion receipts
  while prior object versions survived. Versioned and unversioned loss-of-reply
  recovery plus KYC suites pass **24 cases**. A separate provider-remains test
  verifies durable pending authority, retry count and error evidence; replacing
  version deletion with ordinary deletion in memory makes it fail, and the
  restored test passes. Peer objects and immutable review shells survive.
- Seven existing trip fixtures lacked accepted payout bindings. The baseline
  application reproduces the early admission failure; explicit fixture bindings
  restore the original intended assertions, without changing trip authority.
  The complete affected vehicle/exclusivity/financial-authority files pass
  **41 tests**. Historical migration tests are being reconciled separately;
  no production downgrade guard is relaxed.
- All **518 frontend tests in 94 files** pass with coverage, followed by passing
  TypeScript, ESLint and production build. Pinned Node 26 exposes native global
  Web Storage inside Vitest workers; `execArgv` disables that experimental global
  so the configured jsdom storage works. The unchanged six report-panel tests
  failed before this runner correction. No test assertions or package scripts
  were weakened; this configuration change belongs in the controlled C36 receipt.
- Historical migration rechecks pass **13 cases**: target 0030/0031/0069
  backfill/downgrade assertions now run at their named revision, while empty
  full-head cycles and head schema checks remain. The three money fixture
  failures also reproduce on the baseline 0084 chain. Catalog drift mutations
  use a leaf primary key now that audit events have a restrictive subject FK;
  all eight mutation/restore assertions remain. Exact head/inventory obligations
  include all four approved migrations. Evidence: migration baseline/recheck/
  green logs under `/tmp/mobility-macro-a-*`.
- The administrator creation UI additionally demonstrates masked required proof,
  exact form submission, clearing after a rejected submission, and removing the
  proof field when selecting an ordinary role. Removing the proof field causes
  an observed regression failure; the restored UI test and TypeScript pass.
- All nine pre-existing untracked hashes were rechecked unchanged on 7 Sep;
  all 37 canonical rows occur exactly once, both refs remain at the required
  baseline, and the index remains empty.
- Current architecture inventory is **122 tables / 88 linear migrations** ending
  at 0088. P10's additional CLI/component/authority cases pass **60 tests**;
  the preceding readiness/architecture complement passed 70. Cached predecessor
  image labels resolve to actual heads 0082 and 0071, not current 0088; neither is
  accepted as a capable previous-image recovery rehearsal.
- Sole controller owns synthetic local services `mobility-correction-postgres`
  (60268), `mobility-correction-minio` (64252), and isolated Redis/ClamAV through
  `mobility-correction-relay` (58126/58125). Redis/ClamAV use the internal
  `mobility-correction-services` network; ClamAV updates are disabled and cached
  images/signatures are used. The two scanner integration tests accept an
  explicit local port, retaining default 3310. At programme closure remove only
  these task-owned services/network; never touch unrelated services. Evidence:
  `/tmp/mobility-correction-test-env.sh`, `/tmp/mobility-macro-a-*.log`.
- The 333-case backend focus run measured current product code: 332 pass,
  one already-collected publication warning assertion fails because in-process
  Alembic disabled its logger. The corrected test passes when deliberately
  starting with that logger disabled. No cleanup assertion changed. Full
  frontend coverage now passes **519 tests / 95 files**; changed frontend
  coverage is 92.7273% line / 87.3016% branch.
- Stable full verification is divided into two disjoint test-file sets:
  `test_migration*.py` uses its isolated disposable databases; all other files
  retain the complete PostgreSQL/Redis/MinIO/ClamAV integration configuration.
  Both run under coverage against the same unchanged product files, then their
  data is combined by coverage.py. This changes neither collection obligations
  nor instrumentation and creates no additional implementation owner. Evidence
  inventories/logs are `/tmp/mobility-macro-a-migration-files.txt` and
  `/tmp/mobility-macro-a-verified-*.log`. The earlier exploratory run remains a
  failure inventory, not final coverage authority.
- The exploratory full run finished **2,686 passed / 24 failed / zero skips**
  in 53 minutes. Its application modules and tests were collected before several
  recorded fixture corrections; its coverage is not final authority. The final
  failure inventory also exposed two incomplete trip-payout fixtures, a stale
  pilot test-node reference, a missing synthetic report input hash, the owned
  browser server's build lock, and a crash test's obsolete cleanup expectation.
- The two trip tests and three load-harness failures reproduce against baseline
  application source. Trip tests now use full financial authority and explicitly
  frozen classifier settings, with PostgreSQL for payout processing; old
  authorization bypasses and duplicate rule creation are removed. All **10 trip
  seal tests pass**, retaining quarantine/tamper, audit, day and recomputation
  assertions. The synthetic report fixture gains its actual canonical input
  hash and a recalculated fixture seal; the renderer, cohort and amounts are
  unchanged. A new input-hash assertion failed before correction. Pilot
  preparation references the existing renamed paid/failed-finality test, keeping
  node-existence validation. Load/preparation checks pass in the 27-pass focused
  complement; no live evidence or historical report is changed.
- The process-kill report test now demonstrates the C04-required outcome: one
  registered unsettled object survives, later generation reaches READY with two
  settled receipts, and no object key is duplicated. An in-memory child-worker
  mutation settling before the call fails the new receipt assertion; restored
  crash and commit-replay checks pass. The persistent synthetic provider now
  supplies verified single-version deletion for the shared storage contract.
- The task-owned Next server on 34217 was identified and stopped through its
  original tool session, releasing its build lock. The complete W403B correlated
  synthetic browser journey then passes; unrelated frontend service 3100 was
  untouched. Evidence: `/tmp/mobility-macro-a-w403b-browser.log`.
- All **195 migration tests pass** under fresh coverage in 11 minutes. The
  complete inventory is **231 files = 78 migration + 153 other**, disjoint with
  no omissions. The other-file run is active against stable product bytes with
  every local integration required. Fresh data files are
  `/tmp/mobility-A-verified-migrations.data` and
  `/tmp/mobility-A-verified-other.data`; combine only these completed green runs.
- The query-plan failure showed PostgreSQL selecting the equally selective
  entity index instead of the expected action index. Adding repeated historical
  actions on the same two entities makes the intended selectivity distinct; all
  exact index and result assertions remain. Five consecutive PostgreSQL runs
  pass after the observed failure. Evidence: query-plan-repeat-26 (red) and
  query-plan-stable (green) logs. Stable non-migration verification, combined
  coverage/provenance and the Macro-A independent review remain pending.


**Verification recovery, 8 Sep 2026:** On resumption, both required refs still
match 00918531 and the index is empty; the correction diff remains present.
The prior `/tmp/mobility-*` evidence and service leases are unavailable. The
interrupted non-migration run has no verifiable completion outcome and is not
accepted. Prior observed red/green results remain recorded above, but their
missing raw temporary logs cannot be supplied to the reviewer. Fresh full
verification is rerunning both disjoint shards, with durable logs, exit codes,
source hashes and coverage under ignored `coverage/correction-sep8/`; never
substitute the older `coverage/.coverage` or stale backend LCOV. Frontend coverage
is being renewed there as well. No product change is required by this restart.
The sole controller owns new `mobility-correction-sep8-{postgres,minio,redis,
clamav,relay}` containers and the internal `mobility-correction-sep8` network.
Ports are PostgreSQL 60329, MinIO 60332, Redis 60341 and scanner 60340; synthetic
configuration is `coverage/correction-sep8/test-env.sh`. Cached images only;
scanner updates disabled. PostgreSQL, Redis and scanner readiness passed, and
the owned private bucket was created. The differently configured, stopped
`mobility-correction-postgres` container and unrelated running services were
left untouched. At closure clean only the new owned leases, retaining evidence.
Fresh frontend verification passes 519 tests/95 files, TypeScript, ESLint and
production build. All nine pre-existing untracked hashes still match. The final
runbook inspection corrected C02's obsolete orphan log name and manual recovery
wording: reconstructed bounds and current retention authority govern DROP;
manual FINALIZE alone cannot authorize destruction. Runtime source is unchanged.
Preserved W401C browser checks pass separately without skipped cases: Pixel 7
Start/End with durable synthetic evidence, and iPhone-sized degraded authority
preventing Start. These are browser simulations, not physical-device proof.
Source/test hashes still match the verification-entry fingerprint.
The fresh migration shard passes **195 tests / zero skips** in 674 seconds,
with one existing TestClient deprecation warning. Its exit-code file is zero and
coverage is durable at `coverage/correction-sep8/migrations.data`. The other
shard contains 2,526 tests; together they match all 2,721 collected cases.
The non-migration shard finishes **2,525 passed / one failed / zero skips** in
2,359.91 seconds. The one failure is W403B browser Start blocked by a live
capability check. The unchanged correlated journey then passes once under
coverage and three more times individually. Its aggregate-only cause remains
unresolved and is explicitly submitted as a review risk, not hidden by a claim
that the aggregate itself passed. No capability check or test assertion changed.
Fresh coverage combines the migration shard, full other shard and focused
browser recheck; every one of the 2,721 collected tests has an observed pass.
The controlled C36 refresh passes: changed **94.2804% line / 88.6076% branch**,
global **87.1623% / 64.0758%**, backend **91.5705% / 77.2131%**, frontend
**62.9941% / 47.3424%**. Trusted floors and instrumentation remain unchanged.
The refreshed receipt and separate provenance verification pass. Post-browser
product/test fingerprints match; Ruff and diff checks pass. Evidence is in
`coverage/correction-sep8/{other,browser-recheck,browser-repeat-*,coverage-refresh,
coverage-provenance}.log`, with fresh coverage data alongside.
The sole Macro-A reviewer is **GPT-5.6 Sol / medium**, explicitly selected by the
owner for this multidisciplinary review; the owner amendment supersedes the
usual high-reasoning preference. Its ownership is read-only assessment of the
complete Macro-A diff, contract and evidence; it may not edit or spawn agents.
The review also covers the unavailable prior raw red/green logs and unresolved
aggregate-only browser failure. Macro B remains unstarted until review findings
are resolved and affected verification passes.


**Macro-A independent review — Sol/medium, 8 Sep: FIX (one P1).** The sole
reviewer checked all 120 entry hashes, all Macro-A IDs, the integrated security,
privacy, storage, migration, concurrency, publication, contract and recovery
boundaries. No material product defect, unsafe shortcut, unjustified file or
Macro-B implementation was found. The one P1 is the non-green aggregate browser
journey: four isolated passes do not explain the missing live capability. The
reviewer requires exact failure assessment/trace and a faithful rerun of only
the non-migration shard. Lost earlier raw red/green transcripts remain a disclosed
provenance limitation; the reviewer did not require recreating every mutation.
C34 and the existing external gates remain open.

The controller's bounded review fix adds a privacy-safe browser-console
assessment exactly when Start refuses, before its normal lock cleanup changes
the diagnostic state. It includes capability codes/results/actions, never
identity, GPS, tokens or credentials. This is verification observability only;
no Macro-B behavior or tracking decision is implemented. The W403B test retains
its exact active-health assertion, attaches the assessment on failure, rethrows
the failure and retains a browser trace. A new regression first failed because
no warning existed, then all **43 tracker tests pass**. A temporary test-only
missing-service-worker mutation fails that same browser assertion and captures
`SERVICE_WORKER_NOT_REGISTERED` plus the trace; the fixture was restored before
verification. TypeScript and changed-file formatting pass. Evidence:
`coverage/correction-sep8/start-diagnostic-{red,green,browser-mutation}.log` and
`start-diagnostic-mutation-trace.zip`.

The complete refreshed frontend suite passes **520 tests / 95 files**, and
ESLint passes. The ordinary build retry failed in unchanged Next/Google Font
loading when a font download timed out. No external retry is authorized. The
exact cached font binaries and source-map CSS are preserved with hashes under
`coverage/correction-sep8/cached-fonts/`; a separate production build **passes** using Next's font-response injection
and those exact assets served on loopback, with OS-level non-local outbound
network denial. This is explicitly cached-font build evidence, not a claim that
the ordinary external font-fetch dependency is available. Product font files,
font choices and dependencies remain unchanged. The temporary loopback font
server was stopped after the successful build.

The initial diagnostic rerun was interrupted before completion to impose the
same OS-level non-local outbound network denial; its partial log is retained as
`other-review-partial.log` and is not acceptance evidence. The faithful
153-file / 2,526-test rerun is active in the same order with that denial and
the cached-font response map. The loopback-only font server was restarted for
this run and must be stopped when it finishes. The original failed run is
preserved as `other-first.{log,data,exit-code}`; current outputs are
`other.{log,data,exit-code}`. The unchanged migration pass remains valid.
Frontend coverage/lint and the cached-font production build now pass for the
small diagnostic source change. `source-hashes-review-fix.json` binds the rerun
entry. Reconcile coverage provenance after this stabilizes; do not use the
previous receipt as evidence for changed diagnostic bytes. Resolve this finding
within the same sole review cycle before Macro B; no new reviewer is authorized.

The network-restricted full rerun finished: **2,509 passed, 11 failed, six
setup errors**, with the W403B Start/End browser journey passing in its faithful
aggregate position. Its immutable outputs are now
`other-network-restricted.{log,data,exit-code}`. The runner's outbound restriction
also denied local Unix sockets: Docker-dependent checks and GPG could not reach
their local services. The corrected `local-only.sb` allows loopback IP and local
Unix sockets while still denying other outbound network access. All **11 failed
checks pass** unchanged under that corrected profile (`sandbox-socket.log`).
An initial focused selector truncated one parameter containing a space; its
collection error is retained separately and is not test evidence. The six
frontend-image setup errors remain to be reverified; production/test bytes have
not changed. The standard image build has no cached-font injection interface,
so an explicitly offline image-build probe is checking available local build
inputs before deciding whether external dependency access is mandatory.
Do not claim a green full shard, refresh final coverage provenance, accept A,
or start B from these partial/complementary results. The owner requested no
continuous output polling; completion is awaited without repeated log reads.

**Remaining mandatory local evidence / external-access decision:** the isolated
standard-Dockerfile probe used the already-cached pinned Node image, the legacy
local builder (avoiding registry metadata resolution), `--pull=false` and
`--network=none`. It failed at `npm ci`: uncached pinned package downloads cannot
resolve in that isolated build (`offline-image-probe.log`,
`offline-image-npm.log`, repeated `EAI_AGAIN`). This does not claim that the
separate BuildKit dependency cache is absent. The unchanged standard frontend
build additionally needs Google Font responses, as the earlier normal-build
failure demonstrated; only the explicitly injected cached-font build has
passed for the new diagnostic bytes. The standard Dockerfile has no such
injection. A read-only dependency-download allowance is therefore requested
before running the standard image verification; the owner's prohibition on
external contact remains in force until answered. No production, provider,
publication or deployment action is requested. The stopped probe container and
its two new intermediate images were removed; the owned loopback font server
was stopped. Other task-owned local services and all evidence remain available.
On allowance: verify the six image cases, complete the faithful corrected
non-migration run, refresh coverage from accepted evidence, and obtain bounded
resolution from the existing Sol/medium reviewer. A remains unaccepted, B
unstarted, and no handoff or additional reviewer is authorized by this pause.

**Owner amendment, 8 Sep — review evidence before download authorization:**
Unrestricted internet access is not a default remedy. Present the aggregate-
position browser pass and the corrected 11 local-socket passes to the existing
Sol/medium reviewer in its same review cycle. Ask whether the original P1 is
resolved and whether the six exact standard-Docker-image checks may remain an
explicit external dependency-availability gate. Explain both the original Unix-
socket setup failures and the separate offline npm/Google Font limitations;
neither substitutes for a successful exact image rebuild. Do not construct
substitute evidence, change product code or tests, or start B unless the reviewer
accepts this treatment. If it requires a green exact shard, return to the owner
for narrowly scoped, one-run download authorization. This supersedes the
preceding proposed allowance-first next step. Dispatch remains **GPT-5.6 Sol /
medium**, explicitly owner-selected for this same bounded review resolution;
ownership is read-only and no additional agent may be created.

**Future reproducibility candidate — outside this programme:** when separately
authorized reproducibility work is planned, assess the standard frontend build's
Google Font download dependency and an approved reproducible asset/cache policy.
Evidence: `frontend/src/lib/fonts.ts`, `frontend/Dockerfile`, and
`coverage/correction-sep8/build-review-fix.log`. This records a future candidate
only; it authorizes no font, dependency, Dockerfile or product change in C01–C37
or H07 and creates no new executable queue item.

**Same-review resolution — Sol/medium, 8 Sep:** the reviewer explicitly resolved
the original browser P1 using the diagnostic red/green and aggregate-position
pass. It accepted the six unchanged exact standard-image cases as an external
dependency-availability gate for Macro-A acceptance, without release/deployment
readiness. It does not require another full non-migration run: 2,509 aggregate
passes plus 11 corrected local-socket passes account for all other cases. Its
remaining FIX was only the stale coverage/provenance receipt; no product change
or substitute image evidence was requested. This replaces the earlier local
requirement for a green exact shard; the image gate stays explicitly open.

The controlled C36 receipt now uses only current accepted executions:
`migrations.data`, `other-network-restricted.data`, `sandbox-socket.data` combined
as `accepted-macro-a.data`, plus the current 520-test frontend LCOV. No earlier
image result, interrupted run or synthetic coverage was substituted. Refresh
and separate provenance verification both pass in
`coverage-resolution-{refresh,provenance}.log`: changed **94.291% line /
88.6076% branch**, global **87.1919% / 64.1092%**, backend **91.5781% /
77.2429%**, frontend **63.149% / 47.3804%**. Trusted D32 floors, policy hash,
eligible inventory and instrumentation remain unchanged by this resolution.
Source fingerprints match except the generated Playwright result receipt;
diff whitespace validation passes. The same reviewer receives this bounded
receipt reconciliation for final acceptance; no new review agent or broad
verification run is authorized or needed.

**Macro-A accepted — same Sol/medium review PASS, 8 Sep:** all seven final
receipt/input hashes matched; controlled refresh and independent provenance
verification resolve the last FIX. The reviewer expressly requires no further
exact non-migration run or local implementation change before B. Original
browser P1 is resolved; six standard-image cases, C34 and existing external
gates remain open. Exactly one implementation-review agent has been used;
the one fresh final specialist/consolidated reviewer remains reserved after B.

**Macro-B entry assessment:** the existing Astra controller retains the accepted
source, contract, ownership and evidence pointers without unresolved repository
conflict or missing product decision. Context and operating performance remain
adequate for direct implementation; completed A alone is no handoff reason.
Continue P06 here under the original reviewed acceptance contract. All sixteen
Macro-B C IDs remain individually `VALID / PLANNED` until demonstrated. No
implementation subagent, second Astra writer or external network allowance is
created by this promotion.

**P06 / C06 demonstrated:** one revoked-admin prefix regression failed against
the original service, leaving the authorized 101st intent pending. Restoring
only the baseline selector in memory makes all four PostgreSQL/SQLite ×
revoked-admin/unexpected-error cases fail; the corrected 29-test worker/R20/R21
suite passes, including durable claim-before-provider, uncertain recovery,
concurrency, migration guards and final authorization. The first fixture used
an invalid user status and was corrected before useful red evidence; its log is
retained separately. Evidence is `coverage/correction-p06/c06-{red,
selection-mutation-red,focused-green}.log`, with coverage in `c06.data`.
The scheduler reuses immutable `worker.payout_submission.failed` audit events
and sorts by the later of intent progress and failure time. It does not bypass
the intent's database transition guard, add a migration, fabricate provider
attempts or change claims/payment history. Failure metadata/logging includes
only the error code/class, never exception contents; failure-journal persistence
errors propagate rather than pretending durable progress. All four cases retain
the 100 denied intents at generation zero, make no provider attempt for them,
and process the later authorized intent on the next bounded sweep. Focused Ruff
and scope inspection pass; final integrated coverage and specialist review
remain reserved for stabilized Macro B. C19–C23 remain independently planned.

**P06 / C19 demonstrated:** six baseline cases lose unresolved flags on newest-
member regrouping, signature departure or insufficient evidence. Removing both
automatic-deletion helpers preserves the original flag ID, evidence, detection
time and authoritative money hold. A seventh baseline-source mutation fails the
PostgreSQL money-lock race's strengthened retained-hold assertion. The corrected
78-case replay/hold/assessment/earnings-release suite passes, including both
existing cross-trip concurrency cases and governed dismissal/redetection.
Evidence: `coverage/correction-p06/c19-{red,concurrency-red,accepted-green}.log`
and `c19-accepted.data`. The intermediate 77-pass/one-failure run exposed one
remaining old test expectation that required deleting the hold after the lock
released; it now requires both exact hold owners and preservation of the original
flag/evidence. No assertion was removed or concurrency barrier weakened.
Latest-member detection, bounded/redacted evidence and review semantics remain;
no migration, reconstruction of previously deleted history or new fraud policy.
Scoped Ruff/diff inspection pass.

**P06 / C20 and C21 demonstrated:** the completed payout/trip complement passes
**99 tests** (`coverage/correction-p06/c20-c21-focused-green.log`, coverage
`c20-c21.data`). C20's baseline produced three failures and one preserved
boundary pass; the corrected four cases pass. Earlier ended/unsealed trips
retain chronological daily-cap authority across mixed prices; an end exactly
at Lagos midnight does not consume the next day. C21's baseline admitted the
pre-start trip (one failure, two boundary passes); frozen-start minus one
microsecond now rejects without creating a trip, while exact start and later
admit through the full production authority. Existing v2/v3 calculations,
correction conservation, exclusive end and mutable campaign checks remain.
Evidence: `c20-{red,green}.log`, `c21-red.log` in the same directory. Focused
Ruff and complete four-file scope inspection pass; no migration or API shape
change. C22/C23 remain individually planned.

**Owner amendment — one bounded standard-image verification execution:** run
only the six existing cases in `tests/test_rel005_frontend_image.py` and their
ordinary image build, with dependency access limited to the pinned base image,
locked npm packages and existing Google Fonts. No dependency changes, substitute
build, font redesign, publication or deployment. Record command, exact revision
and worktree, available image/dependency identities, downloads, complete log
and result. If unavailable dependencies still block the build, retain the exact
failure and six-case external gate; do not bypass assertions or retry beyond
this one-run authority. The separate Google Font reproducibility candidate
remains outside this programme. Host test execution retains the local-only
network sandbox; only the ordinary Docker build's dependency retrieval is
permitted. Final review remains the one reserved fresh Sol/medium agent after
Macro B and integrated evidence stabilize.

**Bounded ordinary Docker verification — PASS:** the six existing cases in
`tests/test_rel005_frontend_image.py` passed, with no skips, in **24.84s**.
This is one configured production-image build and six cases, not six images.
Compiled map/revision survive; runtime map override cannot replace the artifact;
all four missing/changed expected map/revision checks reject. The unchanged
ordinary Dockerfile ran npm build; no font mock, alternate Dockerfile, dependency
change or test substitution. Complete evidence: `coverage/correction-docker/`:
`command.txt` records the exact command, `entry.json` the unchanged baseline SHA
and full entry worktree plus input hashes, `tests.log` the six results, and
`docker-complete.log` every Docker command, complete build output, image inspect,
history and fixture cleanup. `locked-dependencies.json` preserves every available
resolved npm version/URL/integrity from the lockfile.

Base identity remains
`node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`;
BuildKit resolved registry metadata and reused its base and npm-ci layers.
No uncached npm packages or base layers were downloaded in this run. Fresh
Next 16.2.10 production compilation passed with the existing Google Font
arrangement; the log does not expose individual font HTTP requests/cache hits,
so a per-font download inventory is unavailable. The build excludes host
`.next` and `node_modules`; no host font cache or mock was injected.
Output image index
`sha256:b1b4b4ee00e885a2cbca423d6f44330dbdd48757eab4ef3a7c6703687e52d94a`,
platform manifest
`sha256:613392d7c67d49c935d4a479a5ba05d860d4564a1343486fe71deb10999e6500`.
The fixture removed its image. A nonfatal existing Big Shoulders fallback-font
warning remains in the complete log. This closes the six-case execution gate
for these audited inputs; subsequent frontend changes require their affected
checks. It grants no deployment/release acceptance. The one-run download
authorization is consumed; unrelated outbound activity remains blocked and
Google Font reproducibility remains a separately deferred candidate.

**P06 / C22 and C23 demonstrated — P06 locally accepted:** all **108** focused
report/measurement/privacy/publication/adjacent-day correction cases pass,
including real PostgreSQL report-first and correction-first overlap. The
127 preserved queue/protocol/PWA/tracker/BFF fixtures also pass; OpenAPI's two
JSON artifacts remain byte-synchronized, with no public DTO shape change.
New runs freeze signed ledger facts, retain original gross-calculation
provenance, and use terminal-period membership consistently in metrics,
daily totals, frozen reports and privacy contributor history. Credits/reversals
remain separately privacy-bounded; voided entries and debt-remainder provenance
cannot double-count cost. Missing calculated-trip ledger authority blocks.
Historical v1 formula reproduction, issued runs and original calculations remain
unchanged; exact retry/repeated source hashes converge.

Three initial PostgreSQL cases reproduced the original correction/cross-period
failures. Seven tests fail with the baseline measurement module restored only
in memory; restoring the baseline report module as well reproduces the eighth,
missing-ledger failure. Added overlap evidence exposed Campaign/Trip inversion
when a correction writer owns Trip before its ledger insert acquires Campaign
FK authority. New issuance takes the existing campaign-terms lock before active
admin and disclosure snapshot locks, matching the production money writer's
ordering. Both directions now finish within the bounded barrier and expose
exactly one old/new ledger position. No lock was weakened, migration added,
financial history edited or external method approval invented.

Evidence: `coverage/correction-p06/c22-c23-{red,authority-mutation-red,
accepted-green}.log`, `c22-missing-ledger-red.log`,
`c22-c23-accepted.data`, `pwa-contract-green.log`, `openapi-check.log`.
Intermediate logs retain the discovered deadlock, a corrected missing test
import, and the initial 102-pass complement; only the final 108-pass run is
accepted for these inputs. Scoped Ruff and diff whitespace/scope inspection
pass. Final integrated coverage and the reserved consolidated specialist
review remain outstanding. All six P06 IDs are independently demonstrated;
P07 now owns C24–C28, and P08 remains unstarted.

### P07 — C24–C28 locally demonstrated (8 September)

C24/C25 persist one exact End manifest (or legacy watermark) before sending,
serialize it with queue writes and receipts, and fence capture preparation,
visibility callbacks and late GPS callbacks by End phase and generation.
Same-page ambiguous End flushes the current trip before reconciliation; reload
retries the durable End without reopening capture. Failed durable End storage
retains evidence and fails closed. C26 reconstructs cancellation independently
from immutable cancellation events and the assignment cutoff; before-cutoff
samples survive, exact/after-cutoff samples cannot enter through ingestion or
quarantine review. No deactivation history is invented.

C27 uses heading [0,360) in the BFF and normalizes invalid optional sensor values
before enqueue/hash, preserving valid peers. C28 stores signed per-sample
results atomically with batch settlement, validates their counts/identity,
shows accepted/rejected/quarantined evidence separately and retains diagnostic
receipts across reload without retransmitting settled batches.

Evidence in `coverage/correction-p07/`: `end-red.log` (3 reproduced failures),
`partial-heading-red.log` (5), `legacy-end-red.log`, `partial-reload-red.log`,
`unit-boundary-red.log` (4 minimal-mutation failures with source restored),
`c26-precise-history-red.log` (3 baseline failures), and
`browser-mutation-red.log` (all 3 browser regressions fail under restored unsafe
boundaries). Green: `final-pwa.log` **141 passed**, `c26-final-green.log`
**63 passed**, `browser-final-green.log` **3 passed**, plus type/lint, scoped
Ruff and diff checks. `browser-partial-retained.png` visually inspected.
Browser cases use actual Next/IndexedDB/WebCrypto/Web Locks with explicitly
synthetic GPS/server receipts; PostgreSQL tests exercise real backend receipt
and cancellation authority. No physical GPS, device or provider claim follows.
No migration or public contract shape changes. P07 diff reviewed for scope;
A's accepted diagnostic source remains preserved. P08 now owns C29–C33.
Final integrated coverage and the reserved fresh Sol/medium review remain due.

### P08 — C29–C33 locally demonstrated; integrated verification open (8 September)

C29's two forms bind uploaded IDs and upload request IDs to exact File objects
and access context. Changed form generations reject stale async completion;
unchanged retries retain the original request/body and cached IDs. Person-form
success resets its captured form element safely after asynchronous work.
C30 shares current-approval convergence under the locked application and work
eligibility authority on person/payee and vehicle decisions and exact retries.
Vehicle retry still replays its original immutable decision, but current
eligibility alone controls convergence. Normal person-first submission remains;
review-order tests use an explicitly seeded expired prior-person projection and
an allowed replacement submission. No expiry worker is invented by that fixture.
Approval does not activate the invited user or duplicate review/terminal audits.

C31 keeps a successfully created campaign ID in the recovery URL. Retry uses
only the existing creative-attachment API; exact managed-file retry already
converges there. Reload and campaign detail expose creative-only recovery;
basics cannot be reopened for editing through this flow. After reload, reselect
only missing creative files; already attached items remain on campaign detail.
An actual browser also exposed Continue's button-type transition submitting the
form before explicit review confirmation. Preventing that default click action
preserves the explicit Create/Attach step; no broader wizard redesign was added.

C32 supplies the ordinary local demo's frozen legacy-compatible payout binding,
synthetic financial reservation, immutable activation snapshot and time-limited
installation/display-proof records. It consumes the unchanged production Start
checks; no auth, evidence or money bypass was added. Fictional identity/account
values use actual configured envelope encryption. These records are explicitly
synthetic fixtures, not real bank verification, provider objects, credit approval
or physical installation evidence. Existing frozen/history rows survive reruns.
The R59-only authority insertion block is removed; its existing preflight now
checks the ordinary seed. Live gates and normal configured evidence-policy
requirements remain. No external provider connection is made by this seed work.

C33 isolates unexpected email-item failures with sanitized warning/audit evidence.
Due ordering includes the durable last unexpected failure so a persistently
failing oldest prefix rotates. Uncertain claims remain untouched until expiry,
then recover even above the normal handled-failure cap with the same provider
key. A failed failure-journal commit propagates. The job remains selection and
composition only; domain helpers own failure history and its ordering expression.
The architecture test retains its exact import and forbidden-write checks with
the two newly required domain helper names. Notification audit targets resolve
to the exact recipient under C14 without importing another tenant's events.

Evidence under `coverage/correction-p08/`: C29 `c29-red.log` (7 failures/1 pass),
`c29-green.log` **9 passed**; C30 `c30-final-red.log` (3 failures/1 pass),
`c30-final-green.log` **31 passed**; C31 action/UI red logs (2 failures each)
and `c31-first-green.log` **6 passed**; C32 `c32-red.log` reproduces production
Start rejection and `c32-full-green.log` **22 passed**, including migrated
immutable guards, rerun preservation and ordinary API Start/End; C33
`c33-final-red.log` (4 reproduced unexpected exceptions) and
`c33-final-green.log` **68 passed**, including PostgreSQL/SQLite fairness,
claim recovery, durable recipient relationships and worker process recovery.
`browser-mutation-red.log` reproduces all three C29/C31 scenarios against the
unsafe boundaries; all source is restored and `browser-final-green.log` reports
**3 passed**. Initial fixture mistakes and the caught architecture-placement
failure remain in their original logs and are not accepted evidence.

P08 introduces no migration or public API shape change. Type/lint and focused
Ruff pass before final integration. `coverage/correction-final/` records fresh
input hashes, exact commands and full logs for the aggregate backend/frontend
checks. The six Docker cases retain their already-recorded bounded six-pass
receipt; that earlier image does not contain subsequent B frontend edits, and
no second dependency-enabled image build has been authorized. No final review,
release or deployment acceptance is claimed yet. The sole reserved fresh
Sol/medium final specialist/consolidated review may start only after integrated
evidence stabilizes; all substantive findings must be resolved in this session.


### Integrated verification — in progress (8 September)

Fresh migrations: **195 passed** in `coverage/correction-final/migrations.log`;
exact command, input hashes and coverage data are adjacent. The remaining backend
aggregate initially stopped at collection because a pre-existing dispute test
imported C19's deleted automatic-removal helper. That test now invokes the detector
and still asserts preservation of the exact disputed flag and its evidence;
`disputes-final-green.log` passes all 8 dispute tests. The original collection
failure is retained as `other-collection-failure-other.log`. The full aggregate
is running again without omitting that module or reducing an assertion.

Frontend: **554 passed / 98 files** in `frontend-final-green.log`, with final type
check passing. Two added frozen-End protocol regressions fail under the isolated
missing-retry mutation (`tracker-restored-final-red.log`) and pass with the exact
implementation. C31's recovery-page authorization/unavailability regression adds
5 observed baseline failures plus the unchanged normal-create case
(`coverage/correction-p08/c31-page-red.log`). The initial V8 LCOV contained a
negative branch count and was rejected by the unchanged coverage checker; its
raw input is retained in `frontend-first-invalid.lcov`. Explicitly pairing the
selected End protocol's request with its completeness value removes that
instrumentation ambiguity; the measured LCOV now parses strictly. No coverage
count was rewritten, branch excluded or floor weakened. Final lint, regenerated
OpenAPI byte check and repository Ruff pass; final combined coverage remains due.

Integration complements now pass: **28** dispute/cancellation/payout-worker/email
cases (`integration-complement.log`) and **9** R08 authorization cases
(`r08-integration-green.log`). C26's older cancellation test now proves one valid
pre-cutoff sample plus one signed post-cancellation rejection, exact receipt
retry and preserved historical financial cutoff; omitting cancellation authority
makes it fail (`c26-integration-red.log`). The current architecture distinguishes
previously retained non-economic evidence from newly unauthorized capture.
The two C06/C33 logging probes reproduce Alembic fileConfig's disabled imported
logger state (2 failures in `logging-isolation-red.log`); each test now restores
only its own logger with scoped monkeypatching, and the same probe passes both
(`logging-isolation-green.log`). Product logging and all fairness/audit assertions
remain unchanged. R08's measurement argument is now a valid typed request so it
can acquire the required campaign-terms lock before active-admin authority;
all 44 call sites, denied-without-mutation checks and the three PostgreSQL
serialization directions remain covered without weaker barriers/assertions.
The accepted final tracker also passes all three real-browser fault scenarios
(`offline-browser-final.log`); coverage, request signatures and receipts remain
unaltered by the diagnostic/mutation harnesses. The full backend shard finished with **2,542 passed / 12 failed** in 42m01s,
with no skips. Its 12 failures are exactly the older C26/C33 expectations,
C06/C33 imported-logger isolation and R08's untyped measurement placeholder
recorded above; all affected complete modules now pass in the **28 + 9 + 41**
integration complements. The final 41-case worker/email complement also retains
first/third-item completion, uncertain second-item claim and same-key expiry
recovery; baseline email-sweep restoration fails that regression
(`email-worker-red.log`). No product safeguard was weakened to satisfy an old
expectation. This is a completed aggregate with resolved focused complements,
not a claim that the raw 2,554-case shard was entirely green in one invocation.
The aggregate-position W4 browser and local-socket cases pass in that same shard.

Final combined coverage (`coverage-verified.json`): changed **95.4325% lines /
87.8623% branches**, global **87.5272% / 65.2964%**, backend **91.6353% /
77.4003%**, frontend **65.6889% / 50.2389%**. C36's controlled refresh records the
current complete inventory and source/policy hashes only after the trusted
ancestor floors and unchanged 90/80 changed-code ratchet pass; a second strict
provenance check passes. The complete measured inputs and combine/refresh logs
are retained under `coverage/correction-final/` rather than pasted here.

The ordinary host production build was attempted with outbound access blocked
and failed retrieving the existing Google Fonts (`frontend-build.log`). No font
substitute, dependency change or additional download permission was used. The
already-accepted six Docker cases remain tied to their earlier exact input
manifest, not to later B frontend changes. Final-image execution, C34 and the
existing live/device/provider/legal/release gates remain explicit for the final
review. All nine pre-existing untracked file hashes remain unchanged
(`preexisting-preservation.json`); HEAD and baseline remote ref are unchanged,
branch `master`, staged index empty. The controller has inspected the complete integrated diff scope. The reserved
fresh Sol/medium final specialist/consolidated review is now admissible; its
verdict and any remediation remain due.


**Reserved final review dispatched:** `/root/final_integrated_review`, fresh
GPT-5.6 Sol / medium, 8 September. The owner explicitly mandates this model and
reasoning for the complete security/privacy/money/migration/concurrency/storage/
recovery specialist and consolidated review. Ownership is read-only over the
unchanged approved contract, full integrated diff, 170-file manifest, evidence
and gates; no implementation or nested agents. The controller remains the sole
Astra writer. This uses the second and final implementation-review slot; any
substantive remediation returns to this same reviewer, not another dispatch.
`coverage/correction-final/` holds the exact review packet and final provenance
receipt. Only this review-status ledger entry changed after dispatch; no product
or acceptance criterion changed. The first returned report stated PASS/no implementation findings and accepted
the explicit final-image/C34 release gates, but several canonical descriptions
were misassigned (including C13, C22–C25, C28, C37 and H07) and five artifact
paths were inaccurate. The controller withheld acceptance of that written
record and returned it to the **same Sol/medium reviewer** for source/test-cited
C01–C37/H07 and exact 30-artifact reconciliation. This continues the same final
review cycle; no new agent or product edit is authorized or created by it.
The corrected source/test-cited response is **PASS, no findings, no local
acceptance-blocking verification gap**. It individually reconciles all C01–C37
and H07 and the exact 30 added paths/consumers/lifecycles. The corrected record
supersedes the initial labels; condensed receipt is
`coverage/correction-final/final-review.md`. The reviewer explicitly accepts
final-source image/dependency availability and C34 as release/external gates,
not local defects, and requires no additional local implementation or shard
before acceptance. No third implementation-review slot was used.


**Local implementation acceptance — 8 September:** Macro A's accepted Sol/medium
PASS and Macro B's corrected final specialist/consolidated Sol/medium PASS are
preserved. Every canonical row above is reconciled: C01–C33 and C35–C37 are
`VALID / IMPLEMENTED`; C34 is `EXTERNAL VERIFICATION REQUIRED`; H07 is implemented.
The six duplicates create no additional work. All owned local behavior is
demonstrated and no actionable review finding remains. This does not mark the
entire correction programme, original executable queue, release or deployment
complete. The original queue/controller authority is unchanged.

Confirmed invariants remain: immutable financial/review/audit/issued-report
history, active-admin/password/session authority, current privacy/consent,
exact storage origins, ordinary fail-closed readiness, stable provider claim
keys, accepted payout windows and screen-on-only evidence capture. No unresolved
local evidence is discarded. No dependency, font family/theme or Dockerfile
change, external provider action, commit, push, merge, PR, release or deployment
has been performed. Nine pre-existing untracked hashes remain unchanged.
Final scope is **140 tracked changed files + 30 new owned files**, with the nine
original untracked artifacts excluded. HEAD and origin baseline remain
`00918531b2bb37a1d184d1d4f917f659b9e4d80b`, branch `master`, empty staged index.

Remaining gates: exact final-source image and normal Google Font-dependent host
build; accepted capable predecessor/positive forward-schema rehearsal for C34;
separately owner-authorized commit/exact-SHA CI/final R59 execution; real device/
GPS, live provider/IAM/CORS, legal, staging and pilot evidence. The bounded six-
case Docker receipt remains valid only for its recorded earlier inputs. No new
unrestricted or dependency-enabled network permission is inferred. Google Font
reproducibility is the separately deferred candidate, requiring future owner
prioritization; font consolidation, theme selection and redesign remain outside
this programme. Local behavior is reviewed with no known actionable defects;
release-ready **NO**, deployment-ready **NO** while these gates remain.

**Direct owner authorization — post-remediation finalization (8 September
2026, recorded before any edit):** the owner directly authorizes, outside the
Executable package queue and without reprioritizing it: complete the deferred
frontend font/build reproducibility correction without changing approved visual
behavior; verify the ordinary final-source host and Docker builds; commit the
accepted programme; push `master` only as a verified non-force fast-forward;
then obtain exact-SHA CI and final R59 evidence. Dependency-enabled access is
limited to exact pinned lockfile dependencies, pinned base images and
acquisition of exact retained font assets with compatible licensing. The nine
pre-existing untracked provenance artifacts stay untouched and unstaged. C34 and
the live device/provider/legal/staging/pilot gates remain external and are not
owned here. No deployment, release, PR merge or production infrastructure change
is authorized.

**Font/build reproducibility correction — evidence (8 September 2026):** the
frontend production build no longer contacts Google Fonts. All seven Google
families remain retained because `globals.css` maps each to a retained theme
(Inter to daylight-ops and broadside, Fraunces to ivory-ledger, Bricolage to
danfo, Archivo to hi-vis, Poppins to terra-grain and the Terrax landing, Big
Shoulders to broadside, IBM Plex Mono to the base mono role and coverage), so no
family, weight or style was dropped and no theme was selected. `next/font/google`
treats `subsets` as a preload filter only, so the approved output is 46 faces;
all 46 exact binaries already existed under
`coverage/correction-sep8/cached-fonts/`, every sha256 re-verified against
`hashes.json`, and all 46 independently re-fetched from `fonts.gstatic.com` and
found byte-identical (`live-refetch-comparison.json`). They are vendored to
`frontend/src/fonts/google/` with per-family SIL OFL 1.1 texts under
`google/licenses/` and `google/provenance.json` binding each file to its family,
subset, weight, unicode-range, exact upstream URL and hash. Seven modules in
`frontend/src/fonts/families/` declare them through `next/font/local`, one call
per family and subset because `declarations` applies to every `src` entry; the
root and landing layouts now set the same CSS variables inline. No dependency,
font CDN, Dockerfile, `globals.css` token or theme changed, and
`package.json`/`package-lock.json` are untouched.

Verification: the guard `frontend/src/fonts/vendored-fonts.test.ts` fails 3 of 92
at the pre-fix boundary and passes 92 of 92 after
(`guard-red.log`, `guard-green.log` inside `static-checks.log`). Five one-at-a-time
source mutations — a duplicated face name, a preloaded non-latin subset, a metric
fallback added to Big Shoulders, a metric fallback removed from Fraunces and an
altered Inter unicode-range — are each detected by the specific guard that names
them, and every mutated file was restored byte-identically
(`guard-mutations.log`). The ordinary production build passes with all outbound
HTTP and HTTPS forced through a dead proxy (`frontend-build-offline.log`), and no
`fonts.googleapis.com` or `fonts.gstatic.com` string remains anywhere in `.next`.
A mechanical comparison of every built `@font-face` against the cached Google
baseline, keyed by binary sha256, reports 46 of 46 faces emitted exactly once
with zero drift in weight, style, `font-stretch`, `font-display` or
`unicode-range`, zero family-name collisions and the same latin-only preload set
(`face-tuple-comparison.log`). Eight metric-fallback faces are emitted — Clash,
Satoshi and six vendored families; Big Shoulders correctly has none, matching
`next/font/google`, whose metrics table has no entry for it, and Fraunces
correctly keeps `local(Times New Roman)`. Those override values are now computed
from the vendored binaries instead of Next's precalculated table, so they differ
marginally; this affects pre-swap metrics only, not painted glyphs. Browser checks
against the production server confirm each of the nine themes resolves to its own
typeface, that hi-vis retains `font-stretch: 125%`, and that Yoruba and Hausa text
under hi-vis lazily loads the Archivo latin-ext and vietnamese faces, which a
latin-only vendoring would have lost. 99 frontend files and 646 tests, typecheck
and lint pass. Two defects were found by verification and fixed: the first
implementation reused subset const names across families, which `next/font` turns
into one shared `@font-face` family and which merged all seven typefaces, and the
first guard version accepted a missing metric fallback and a non-latin preload
target. Both are now asserted and mutation-proven.

Final-source image: the six `tests/test_rel005_frontend_image.py` cases pass
against the frozen final source recorded in `final-source-identity.txt`
(`rel005-final-source.log`), superseding the earlier image receipt, which is not
represented as final-source evidence. A separate inspection build of that same
source shows 52 woff2 in `/app/.next/static/media` — 46 vendored plus the six
pre-existing local faces, 34 of them non-latin subsets — zero Google host
references anywhere in `/app/.next`, and the P07/P08 frontend markers present
(`image-content-inspection.log`). Base image `node:22-alpine`
`sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`,
linux/arm64. The production CSP already sets `font-src 'self' data:` and
`style-src-attr 'unsafe-inline'`, so the vendored faces and the inline variables
are both permitted. No contract or generated-artifact input changed, so no
architecture section 9 baseline or R14-B fixture rerun was required. An
independent plan review and an independent post-build minimal-change review were
both obtained and reconciled; the post-build review's P1 finding — that the
typecheck and lint receipts predated the final source — was fixed by re-running
both, which then surfaced three real type errors in the strengthened guard.
Evidence logs are retained under `coverage/correction-fonts/` and are not
committed. The nine pre-existing untracked artifacts remain untouched and
unstaged.

**Exact-SHA CI and R59 — NOT ACCEPTED (8 September 2026):** the programme was
committed once as `bc3c3454f489ba4cc5b4a6c6f56cc3fafe4b90ff` and published to
`origin/master` as a verified non-force fast-forward `ff2225a..bc3c345`, 500
commits ahead and 0 behind, with `origin/master` proven an ancestor. GitHub run
`34276581120` ran against that exact SHA — each job's own SHA-verification step
passed — and **concluded failure**. `lint / types / unit / contract / build`
passed, covering the frontend build, type, unit and generated-contract gates.
`backend lint / tests` failed with 14 failed and 2741 passed in 70m47s. The R59
real-stack release journey failed. `changed-code coverage policy` and `e2e
against the real stack` were **skipped**, because they depend on the backend job,
so those two required gates did not execute and are unevidenced for this SHA.

R59 is not environmental. After the simulated API outage and recovery the
`End trip` control never re-enabled, with the tracker showing `degraded`,
`Pings synced 0`, `Buffered 3` and GPS `Waiting…`. The API container log records
exactly one `POST /api/v1/driver/trips/start` `201 Created`, normal
`trips/current` polling, and no `POST .../pings` or `POST .../end` at all. **The
absent ping POSTs are not themselves the defect:** `FLUSH_INTERVAL_MS` is 15s and
`FLUSH_AT_COUNT` is 20, and the journey's healthy window is roughly six seconds
carrying about three pings, so no flush is due before the outage begins. An
earlier revision of this receipt wrongly presented the quiet healthy window as
evidence of the regression; that reading is withdrawn. The
backend and worker logs show no traceback, no 5xx and a normal SIGTERM teardown,
and the Playwright trace records no console error and no page error, so the app
was hydrated and interactive. R59 **passed** at baseline `0091853`. The failing
assertion is the post-recovery `expect(End trip).toBeEnabled()`: after the
outage-time End freezes the durable boundary, a reload hydrates the tracker into
`endPhase = "submitted"` with `authorityUncertain` set and returns before the
runtime is re-probed, so `assessPilotPwa` never sees `session === "valid"` again
and both the `Reconcile trip` and `■ End trip` affordances stay disabled. The
governed `frontend/e2e/r59-real-stack.spec.ts` is byte-unchanged in this commit,
so the End/recovery affordance changed underneath an unchanged journey. R59 runs
with `retries: 0` by design. This is recorded as a genuine implementation defect
in the P07/P08 frontend correction, surfaced only by exact-SHA CI. No product
code was changed to force green and no further push was made from that state.
Evidence: `ci-exact-sha.log`, `r59-error-context.md`, `stack.log`,
`compose-ps.txt`.

All 14 backend failures pass locally; 11 are demonstrated environmental and 3 are
CI-only with undetermined cause. Demonstrated environmental: the eight
`test_storage_csp_origin.py` cases fail in CI with `ConnectionResetError [Errno
104]` while all eight pass locally in 5.28s against the real Docker-launched
`caddy:2.8-alpine`, so the CI failure is runner container networking; the two
`test_errors.py` R13 budget cases took 6.28s and 9.33s against a 3.0s budget
under `coverage run` on a hosted runner and complete locally in 1.40s; and
`test_recovery_readiness_authority.py::test_historical_predecessor_rehearsal_fails_before_build_or_infrastructure`
fails on `fatal: ambiguous argument '26f5e221…^{commit}': unknown revision`
because the predecessor commit is absent from the CI checkout depth, which is the
C34 external-gate area. Undetermined: the two PostgreSQL cases
(`test_driver_vehicle_approval.py::test_postgres_nin_rewrap_and_trip_share_eligibility_before_profile_order`
expecting `DRIVER_PROFILE_NOT_ACTIVE` but observing
`DRIVER_PERSON_PAYEE_NOT_APPROVED`, and
`test_r20_disbursement_postgresql.py::test_concurrent_claim_commits_before_provider_io_and_submits_once`
observing `query_only` instead of `resolved`) both pass in isolation locally
against a real PostGIS 16-3.4 but fail inside the full CI suite, which points at
ordering-dependent cross-test state rather than an isolated defect; and
`test_w403a_release_preparation.py::test_bundled_tls_rejects_wrong_san` passes
locally but does not raise in CI, which points at platform-dependent TLS SAN
validation. None of these three is demonstrated environmental and none is
reproduced as a product defect, so all three also return to the correction gate.
Evidence: `backend-failed.log`, `local-triage.log`, `local-pg-triage.log`,
`local-csp.log`.

The consolidated post-build minimal-change review of the font/build amendment was
dispatched but never returned a verdict before the session ended; an earlier
revision of this receipt wrongly reported it as obtained and reconciled. That
review is outstanding and is folded into the corrective package's consolidated
review. The repository is therefore **not CI accepted**, **not release-ready**
and **not deployment-ready**, and the font/build amendment's local acceptance
rests on its plan review and verification evidence pending that consolidated
verdict. C34 and the live
device, provider, legal, staging and pilot gates remain external and unmet. This
receipt is written for the next corrective commit; no evidence-only commit was
created for it.

**Direct owner authorization — exact-SHA acceptance correction (9 September
2026, recorded before any edit):** the owner directly authorizes one
Review-Required corrective package, forward-only from
`bc3c3454f489ba4cc5b4a6c6f56cc3fafe4b90ff`, covering (A) the genuine R59 ping
submission/recovery regression and (B) the exact-SHA CI failures blocking
backend, changed-code coverage and real-stack e2e acceptance. No revert, reset,
history rewrite, force-push or additional implementation branch; `origin/master`
is corrected forward only. The accepted font/build work is not to be disturbed.
No implementation subagents; one review-only agent per gate. Environmental CI
failures must be fixed at the real boundary — no weakened assertions, skipped
tests, unevidenced timing relaxations, or mocked-away Caddy/PostgreSQL/TLS — and
anything that cannot be reproduced or confidently classified is retained as
explicitly unresolved rather than guessed. C34's genuinely capable predecessor
and the physical-device, provider, legal, staging and pilot evidence remain
external and unauthorized, as do release and deployment.

**Corrective package — delivered (9 September 2026).** The first Part A
hypothesis is withdrawn. The End control is one button whose accessible name
flips on `authorityUncertain` (`trip-tracker.tsx:1167-1172`), `session` is seeded
`valid` (`:65`), and the failure aria tree shows that button enabled, so no
capability gate was involved. Investigation then found the frozen-End reload
affordance is **deliberate and test-covered** by `bc3c345`: three cases in
`trip-tracker.test.tsx` assert that a reload with a frozen End shows
`Reconcile trip`, re-submits the identical frozen manifest exactly once, never
re-freezes, never forgets evidence and never reopens capture. An attempt to
restore the `■ End trip` affordance broke exactly those three cases and was
reverted; `frontend/src` is byte-identical to `bc3c345`. The genuine defect is
therefore that `bc3c345` left the governed `r59-real-stack.spec.ts` inconsistent
with its own deliberate product change, and the correction is one line plus a
comment in that leased journey. R59's healthy window is ~6s against
`FLUSH_INTERVAL_MS` 15s and `FLUSH_AT_COUNT` 20, so **R59 does not evidence
healthy ping submission**; that property is covered by the component and
ping-queue tests only, and must not be read out of an R59 pass.

Backend item 14 was **reclassified from environmental to a security-relevant
product defect and fixed**: `release_contract.py` treated only a non-zero
`openssl` exit as failure, and `openssl x509 -checkhost` mismatch exit semantics
differ between the local OpenSSL 3.6.3 and ubuntu-latest's 3.0.x, so wrong-SAN
rejection did not fire on the deployment platform. The SAN is now checked
in-process against the certificate's DNS names, deliberately stricter than the
CLI it replaces: a certificate with no matching DNS SAN is refused rather than
falling back to the CN. Wildcard and IP-SAN handling were removed after review
as unreachable dead code that was looser than OpenSSL. Red/green proved by
emulating OpenSSL 3.0 exit semantics: pre-fix `DID NOT RAISE`, fixed raises;
455 module tests pass. This correction still owes the named specialist security
review that this repository requires for security checkpoints; it is recorded
here as an open obligation, not as a satisfied gate.

The eight `test_storage_csp_origin` cases were root-caused to a readiness loop
that caught only `(URLError, RemoteDisconnected)` while Linux docker-proxy
accepts-then-resets during Caddy boot, raising a bare `ConnectionResetError`. The
wait now covers every `OSError`, extends to 30s and fails loudly if the container
exited; every CSP assertion is byte-unchanged. Red/green proved by injecting the
reset: the pre-fix narrow catch raises the exact CI error, the fixed wait passes
all seven parametrisations. The two R13 budgets replaced raw `elapsed < 3.0` with
`_linear_scan_budget`, which times the identical code path on a smaller input of
the same shape in the same process and instrumentation; after review it uses two
references so neither payload size nor nesting depth can hide a regression behind
the other. Red/green proved: a genuinely quadratic redactor breaches both budgets
while the real one passes plainly and under `coverage run`. The backend job now
checks out full history so the predecessor rehearsal fails on capability rather
than on `unknown revision`, preserving C34's external limitation.

The consolidated independent review returned **FIX** and found two P1s that local
runs had missed: `ruff check .` failed on an `I001` import placement and a `B023`
loop-variable capture, either of which would have killed the backend job at lint
before pytest. Both are corrected and `ruff check .` passes. It also removed the
permissive SAN branches, narrowed the nested budget, and surfaced a missing guard
that a declared font face could be dropped from its exported chain and silently
fall back to a system font; that guard is added and mutation-proved.

Items 12-13 remain **explicitly unresolved**: both PostgreSQL cases pass in
isolation, with the backend env block including `F7_SEED_MAX_TRIPS_PER_DAY=1`, and
across both complete modules against real PostGIS 16-3.4. They are retained
unresolved rather than guessed, and the next exact-SHA run is the reproduction.
`test_r13_assignment_scan_is_linear_at_the_candidate_budget` still asserts a raw
`elapsed < 3.0` and is a known latent flake under coverage instrumentation; it is
recorded here so it is not re-diagnosed as environmental.

`.github/workflows/ci.yml` is an R59-leased file, so `R59_LEASED_FILES_DIGEST`
changes with this commit and any earlier R59 receipt is non-representative.

**Exact-SHA CI on `6f5d185` — 14 backend failures reduced to 2 (9 September
2026).** Run `34326905268` against the exact pushed SHA: quality **success**,
**R59 real-stack success** (the regression is closed), backend **failure** with
2 failed / 2753 passed in 1h16m, and changed-code coverage and real-stack e2e
**skipped** behind backend, so those two gates remain unevidenced. Fixed and
confirmed green in CI: all eight `test_storage_csp_origin` cases, the
predecessor-rehearsal revision resolution, the wrong-SAN TLS rejection, the R13
nested-assignment budget, and `test_r20_disbursement_postgresql`.

Two remain, both now evidenced rather than assumed:

`test_r13_malformed_structure_has_bounded_work_and_memory_before_candidates`
failed at 9.264s against a calibrated 1.109s. Local measurement shows
`redact_log_message` is **linear** on this input — 0.115us/char at 50k against
0.108us/char at 500k — so there is no super-linear redaction defect. The fault
was in the calibration itself: the reference was timed after `tracemalloc.stop()`
while the measured call ran inside the tracemalloc window, comparing an
uninstrumented run against an instrumented one. tracemalloc's per-allocation cost
is not a constant wall-clock factor, so the ratio inflated. The reference is now
timed inside the same tracemalloc window with `reset_peak()` between, leaving the
`peak < 8_000_000` assertion measuring only the full-size call. Red/green
re-proved after the change.

`test_postgres_nin_rewrap_and_trip_share_eligibility_before_profile_order` still
observes `DRIVER_PERSON_PAYEE_NOT_APPROVED` where it expects
`DRIVER_PROFILE_NOT_ACTIVE`. It is **not environmental and not a product
defect**: the test orchestrates a NIN rewrap against a concurrent trip start
through `acquire_work_eligibility_lock` and
`_acquire_work_eligibility_authority`, and the assertion depends on which
contender reaches work-eligibility first. The product refuses the trip in both
observed interleavings; only the cited unmet precondition differs. On the runner,
under coverage tracing and a different core count, the interleaving differs from
this machine, where the full 2755-case aggregate passes in 47m. The correct
correction is to make the intended interleaving deterministic rather than to
relax the assertion, and that has **not** been attempted here: it is retained as
the single open backend item, deliberately not patched by guesswork in a race
guard. Its sibling `test_r20_disbursement_postgresql` passed on this run without
any change, which is consistent with scheduling sensitivity rather than shared
state.

Repository status: locally accepted; **not CI accepted**; not release-ready; not
deployment-ready. C34 and the live device, provider, legal, staging and pilot
gates remain external. The TLS SAN correction still owes its named specialist
security review.

**Direct owner continuation — deterministic vehicle-approval race (9 September
2026, recorded before correction):** exact-SHA run `34335514041` against
`e408448cdfdff2aee9daa3de646a241e10758cb9` repeated the sole unresolved backend
failure: 2,754 tests passed and
`test_postgres_nin_rewrap_and_trip_share_eligibility_before_profile_order`
again observed `DRIVER_PERSON_PAYEE_NOT_APPROVED` instead of the intended
`DRIVER_PROFILE_NOT_ACTIVE` interleaving. Quality and R59 passed; changed-code
coverage and real-stack E2E were skipped behind backend. The owner authorizes
one Review-Required, test-only correction that makes the intended lock ordering
deterministic without relaxing either error, adding sleeps/retries, reducing
concurrency or weakening the product eligibility guard. It must reproduce under
coverage and runner-like scheduling, receive independent plan and post-build
review, and move `master` only by a verified normal fast-forward before a new
exact-SHA acceptance run. The nine protected provenance artifacts and all
external/release/deployment gates remain unchanged.

**Deterministic race correction — local evidence:** the test's prior event was
set only after the trip acquired the shared advisory lock, so the conditional
wait could not establish which transaction owned eligibility authority. On the
hosted runner, trip start read the initially active profile before waiting behind
the rewrap transaction; after serialization, its current person/payee query saw
the committed KYC reset and correctly refused work with
`DRIVER_PERSON_PAYEE_NOT_APPROVED`. Faster local scheduling let rewrap commit
before that initial read and produced `DRIVER_PROFILE_NOT_ACTIVE`. Both paths
failed closed, but the test asserted one without proving its ordering.

The corrected barrier now asserts rewrap already owns eligibility authority,
then holds it until trip start signals immediately before awaiting the same
lock. This proves genuine overlap and the exact identity-map/current-KYC ordering
without sleeps, retries, reduced concurrency, accepted-error sets or product-code
changes. With the barrier and old expectation, the focused real-PostGIS test
fails deterministically under coverage with the runner's person/payee result;
with the one exact expectation corrected, eight consecutive coverage runs pass.
The same source passes in a Linux Python 3.12.14 container constrained to two
CPUs and 3 GiB, and the complete vehicle-approval module plus adjacent KYC and
payee PostgreSQL concurrency checks pass 18 tests. `ruff check .`, progress
validation and diff checks pass. The independent Sol/medium plan review returned
REVISE; its truthful event rename, explicit rewrap-ownership assertion and
identity-map explanation are all incorporated. The separately named Sol/medium
TLS security specialist review returned PASS with no security finding, closing
that recorded review gate; its optional direct edge-case test matrix is a
non-blocking P3. The fresh Sol/medium consolidated post-build/minimal-change
review returned PASS with no finding over this correction, the complete
font/build amendment, every post-`bc3c345` correction, evidence truthfulness and
external gates. Exact-SHA CI remains due, so this is local correction evidence
only and no release or deployment status has changed.

**Additional exact-SHA concurrency evidence — correction authorized (9
September 2026, recorded before edit):** run `34344328340` targeted the exact
fast-forwarded SHA `a91ad26dd646faa7a8af62dddf3c050b29514ba6`. The corrected
vehicle-approval race passed; quality and R59 passed. Backend instead exposed
two different pre-existing harness races (2 failed / 2,753 passed), and coverage
and real-stack E2E were skipped. R08 proved through `pg_blocking_pids` that the
protected writer waited behind the disabling transaction and was then denied,
but asserted the order in which two coroutines appended labels after transaction
exit; that Python scheduling order is not database commit order. R20's provider
probe used `FOR UPDATE NOWAIT` while the losing concurrent claimant could still
legitimately hold the same row, so the probe itself raised and the production
failure boundary correctly moved the intent to `query_only`. Both tests pass in
focused local coverage runs, consistent with scheduler sensitivity rather than
an isolated product defect. The owner-authorized exact-SHA correction therefore
extends only to deterministic test barriers in
`tests/test_r08_admin_authorization_postgres.py` and
`tests/test_r20_disbursement_postgresql.py`: prove the committed disabled row
inside R08's denied writer transaction, and let R20's concurrent loser complete
before the provider-side committed-attempt/no-lock probe. Product code, database
locks, failure handling, concurrency, exact outcomes and all external gates stay
unchanged. Independent plan and post-build review, red/green evidence and a new
all-job exact-SHA run remain mandatory.

The independent concurrency plan review returned `REVISE`; its sole required
change was incorporated by bounding R20's coordinated pair with
`asyncio.wait_for(..., timeout=10)`. Run `34344328340` supplies pre-fix red
evidence for both scheduler-sensitive harness failures. After the correction,
five consecutive focused PostgreSQL coverage runs passed (2 tests each), both
changed modules passed together (8 tests), and the adjacent authorization and
disbursement group passed (21 tests). The two corrected races also pass under
the CI Python 3.12 runtime constrained to 2 CPUs and 3 GiB (2 tests). Full Ruff,
progress validation and diff whitespace checks pass. These are local correction
results only; consolidated post-build review and a new all-job exact-SHA run
remain due.

The independent Sol/high consolidated post-build review returned `PASS` with
no findings. It confirmed that R08 retains blocking, denial, persistence and
all 44 migrated call sites; R20 retains genuine concurrent claiming, exact
outcomes, one provider call, committed-attempt/no-lock proof, persistence and a
bounded hang guard; and the ledger truthfully keeps exact-SHA acceptance and all
external gates open. A new all-job exact-SHA run is the remaining acceptance
gate for this correction.

**CI-runtime coverage reconciliation — correction authorized (9 September
2026, recorded before policy edit):** exact-SHA run `34354263174` on
`41d006729a0aa1290a617060e8ea27b956ea4fc5` passed quality/build, the complete
backend suite and R59. Changed-code coverage then failed its exact global ratio
comparison and real-stack E2E was skipped. The downloaded successful backend
and frontend LCOV artifacts measure global 28,513 / 33,491 lines and 7,350 /
12,212 branches, while the committed receipt records 27,326 / 31,220 and 7,974
/ 12,212. No eligible product source changed between the receipt and candidate.
The receipt was generated from the local Python 3.14 evidence set, whereas the
authoritative CI/backend/runtime line is Python 3.12; Python 3.12 alone reports
2,269 covered class annotation-only lines that Python 3.14 largely omits, and
the interpreters also produce different covered branch counts. The owner-
authorized correction is limited to a reviewed, source-bound rebaseline using
the successful exact-SHA CI artifacts and explicit runtime provenance. It may
not change eligible source, coverage instrumentation or exclusions; lower the
D32 90% changed-line / 80% changed-branch floors; treat a skipped job as
evidence; or claim E2E, release or deployment acceptance. Independent plan and
post-build review, deterministic policy tests, provenance verification and a
new five-job exact-SHA run remain mandatory.

The independent Sol/high plan review returned `REVISE` twice and then `PASS`.
The incorporated findings require the producing backend job—not the consumer—to
emit an LCOV-hash, exact-SHA, CPython and coverage.py sidecar; protect that CI
wiring in the policy hash; make unprovenanced v1/v2-to-v3 reconciliation
single-use; and distinguish exact candidate-receipt admission from later
at-or-above-floor verification. GitHub's immutable job log independently records
CPython 3.12.14, coverage.py 7.16.0 and the generating commands; artifact API
metadata binds backend artifact `10109024797` and frontend artifact
`10105098738` to run `34354263174` and exact SHA `41d0067`, with archive and
extracted-LCOV hashes recorded in the fixed attestation. This supports one
reviewed migration without synthesizing producer evidence.

Red evidence: the two new runtime-reconciliation tests failed because the old
checker had no such authority or arguments. Green evidence: all 30 coverage-
policy tests pass, including tampered report rejection, v3 reuse rejection and
sidecar verification. The one-time receipt was generated under CPython 3.12.14
from the exact successful GitHub artifacts and separately re-admitted against
the candidate tree. It records global 28,513 / 33,491 lines and 7,350 / 12,212
branches, backend 25,266 / 28,514 and 4,616 / 6,770, frontend 3,247 / 4,977 and
2,734 / 5,442, plus the seven previously omitted font-family modules as
inventory additions. D32's changed-code floors remain exactly 90% line / 80%
branch; eligibility, instrumentation, exclusions and product source are
unchanged. Full static/document validation and consolidated post-build review
remain due before the normal fast-forward push; five-job exact-SHA acceptance
remains open.

The consolidated Sol/high post-build review initially returned `FIX` for an
unavailable consumer-side coverage.py import and ambiguous patch-version
authority. Both were removed: the checker now passes under sterile `python -S`,
producer coverage.py identity remains receipt-bound, and Python major/minor is
explicitly the measurement domain while the exact observed 3.12.14 remains in
legacy evidence. Re-review returned `PASS` with no findings after independently
rerunning all 30 policy tests, Ruff, diff checks and the receipt policy hash.
Exact-SHA CI remains the sole acceptance gate for this correction.

## Executable package queue

| # | Package | Status | Outcome | Package prerequisites |
| ---: | --- | --- | --- | --- |
| 1 | **PKG-01 — foundations and empirical risk proof** | DONE | Resolve remaining foundations, production-PWA/staging risk and correction authority. | none |
| 2 | **PKG-02 — money integrity and payout operations** | DONE | Corrected release, pre-existing-reversal backfill and debt-aware economic/settlement authority agree. | none — checklist DAG gates entry |
| 3 | **PKG-03 — commercial contracts and billing** | **BLOCKED** | Synthetic/provider-neutral commercial flow and configurable budget enforcement are verified; only `W2-01C BLOCKED — EXT-PAYMENT-PROVIDER` remains unfinished. | none — checklist DAG gates entry |
| 4 | **PKG-04 — secure evidence, activation and communications** | **DONE** | Provider-neutral storage/KYC/activation, shared notifications, business triggers, audited driver contact and account recovery are verified; live providers remain gated. | none — checklist DAG gates entry |
| 5 | **PKG-05 — privacy, measurement and retargeting** | **DONE** | Privacy controls and reproducible measurement govern aggregate retargeting, exposure scores and advertiser insights; live privacy/methodology/platform inputs remain gated. | none — checklist DAG gates entry |
| 6 | **PKG-06 — matching and driver onboarding** | **DONE** | Recommendations, offers, activity, public application, person/payee onboarding and governed vehicle approval form one verified work-eligibility journey. | none — checklist DAG gates entry |
| 7 | **PKG-07 — production driver PWA** | **DONE** | The installable pilot PWA safely tracks, syncs and completes the governed onboarding, campaign, earnings and dispute journey; physical-device/live release evidence remains explicitly deferred. | none — checklist DAG gates entry |
| 8 | **PKG-08 — governed reporting and pilot readiness** | **BLOCKED** | Provider-neutral reporting, release preparation and synthetic pilot acceptance are reviewed and complete; only registered external deployment, provider, approval, device and pilot evidence remains. | none — checklist DAG gates entry |
| 9 | **PKG-09 — controlled pilot, training and handover** | **BLOCKED** | Provider-neutral training, pilot-operations and handover preparation is integrated and reviewed; only rehearsed training, controlled-pilot evidence, named-owner acceptance and protected handover remain. | none — checklist DAG gates entry |
| 10 | **PKG-10 — admitted Cardvert audit remediation** | **DONE** | All 86 admitted FIX candidates are delivered and verified once through the exact R01–R60 dependency graph; all 29 non-executable dispositions remain preserved. | none — remediation DAG gates entry |

## Executable package contracts

### PKG-01 — foundations and empirical risk proof

- **Owns:** checklist 1–9. D23 separates runnable build evidence from later
  real-world validation without weakening any real-GPS, release or pilot gate.
- **Closure:** production-PWA protocol and interrupted synthetic-flow build proof,
  provider-neutral production-like release/recovery proof, RM2/RM6/RM7
  corrections, required reviews and exact CI agree. Physical-device/route/
  battery and external-staging evidence remain explicitly incomplete post-build
  validation until their registered inputs and later pilot/release gates exist.
- **Package plan (activated 16 Aug 2026, canonical branch `feat/pkg-01`):**
  internal checkpoints under the controller's disjoint-ownership rule.
  Canonical/controller work: **FND-07** (first runnable checkpoint — integrity
  409 envelopes, RM7), R14-B device evidence after R14-A integrates, aggregate
  verification and every control/authority-document update. Delegated
  contributor branches (integrated only by the controller, never self-merged):
  `feat/pkg-01-pro-pwa-contract` → R14-A ADR/capability contract;
  `feat/pkg-01-pro-money` → MNY-06A/B/C chain. FND-02A is a prepared decision
  packet (parameterized options + executable fixtures + independent
  product/money review) resolved by D22's owner-selected synthetic Option A;
  `EXT-RM2-POLICY` is present and FND-02B implements it on the MNY-06 binding.
  R14-A/B and R17-A close only on their automated/synthetic build contracts;
  D23 records physical-device and external-staging execution as deferred,
  incomplete validation rather than fabricated evidence or a build blocker.
- **FND-07 evidence (DONE 16 Aug 2026):** candidate `58794a4` on
  `feat/pkg-01` (collateral model-drift fix `139bfcb`). Four exclusivity
  constraint names registered in the `app/db/integrity.py` classifier; lost
  races at assignment create/activate and trip start translate to the same
  stable 409 codes as their pre-checks; unrelated integrity failures re-raise.
  Verified: `tests/test_integrity.py` + `tests/test_exclusivity_conflicts.py`
  (pre-check-defeated API envelopes, PostGIS two-transaction races), full
  suite 501 passed on PostGIS, regenerated contract artifacts byte-identical
  (no §9 movement), CI green (backend, contract-drift, e2e). Independent plan
  review PASS and independent API/concurrency checkpoint review PASS against
  the exact candidate. Architecture v1.25; §35.1 RM7 closed.
- **MNY-06A/B/C evidence (DONE 20 Aug 2026):** Fable/Codex recovery lane
  `feat/pkg-01-fable-money` integrated at reviewed tip `25fdd52`. Migrations
  `0018`–`0021` add append-only effective-dated payout revisions, acceptance-time
  bindings with frozen rates/cap/eligibility and premium/exclusion geometries,
  and maker-checker correction orders. `payout_v3` pays valid outside-premium
  time at base and inside-premium time at premium, preserves the shared
  chronological Lagos-day cap, persists exact tier components, and never
  reprices accepted work from later rule/zone/settings changes. Direct
  recompute is retired behind projected orders; creator self-approval fails,
  positive deltas require their own release time, and execution/replay is
  idempotent. Admin revision/correction screens and driver tier explanations
  shipped with all three §9 baselines. Verified: PostGIS backend 562 passed
  (3 expected skips), migration up/down/re-upgrade + autogenerate-empty,
  frontend 155 tests/typecheck/lint/build, live-stack Playwright 22 passed,
  and a two-admin synthetic maker-checker journey. Exact-candidate
  money/security, architecture/concurrency/frozen-terms, and minimal-change
  reviews all PASS with no remaining P0–P2 findings. Architecture v1.28;
  §35.1 RM6 closed.
- **FND-02A/B evidence (DONE 20 Aug 2026):** D22 records the reviewed,
  provisional 120-second/25-metre/2-confirm/1-release per-trip policy for new
  acceptances. The classifier combines deterministic rolling displacement with
  the existing long-stay path before one shared grace allocation; complete
  common and rolling terms plus `stationary-rd-v1` freeze into payout-v3
  bindings/fingerprints, while payout-v2 metadata/fingerprints remain exact.
  Payout and correction evidence persist the stationary reason/detector proof,
  and driver/admin surfaces explain it. Focused PostGIS classifier, binding,
  payout and correction suites passed; historical NULL revision overlays are
  read compatibly as `{}`; frontend explanations and the live desktop/mobile
  payout-rule journey passed. Architecture v1.30; §35.1 RM2 closed.
- **R14-A build evidence (DONE 20 Aug 2026):** Pro
  contribution `bc64707` (parent `e74412c`, six new files) verified
  (merge-base, manifest, 123-test/typecheck/lint/build preflight reproduced)
  and squash-integrated with two review-driven corrections in the canonical
  commit: capture/`health=active` requires a valid session or explicit
  `activeTrip` continuation, and probe evidence is labelled and documented as
  capability-only, never runtime lock ownership. Independent
  PWA/security/architecture review corrections and the D23 deferred-gate
  specialist corrections are integrated. ADR 014; architecture v1.30.
- **R14-B/R17-A build evidence (DONE 20 Aug 2026):** deterministic queue,
  tracker, seal and capability checks passed; the complete live browser suite
  passed across desktop/mobile profiles (55 passed, 3 intentional skips).
  Production Compose/edge configuration, release/recovery contracts and Caddy
  validation passed provider-neutrally with synthetic data. The three deferred
  rows below remain `NOT RUN`; no physical-device, route/battery or external
  staging evidence is claimed, and their later real-use gates are enforced by
  the progress validator.
- **Control-plane remediation (16 Aug 2026, task-master correction):** the
  queue validator now rejects six independently reproduced bypass classes
  (hidden/fenced decoys, shadow documents, REVIEW pause-avoidance, frontier/
  QUEUED-DONE drift, Owns drift, external-id erasure) and `EXT-REPORT-METHOD`
  moved from W4-02B's build prerequisite to W4-03B's live pilot gate to match
  the register's recorded semantics. Closes no checklist item; validator +
  33 tests green; architecture v1.26.

### PKG-02 — money integrity and payout operations

- **Owns:** checklist 10–18. One plan integrates assessment/hold, release,
  protected payee, reservation/reconciliation and post-payment debt semantics.
- **Package plan (activated 21 Aug 2026, canonical branch `feat/pkg-02`):**
  controller Lane A owns MNY-08A → MNY-09A → MNY-08B, then MNY-08C and
  MNY-03A. The separately commissioned GPT-5.6 Pro Lane B attempt produced no
  durable files, migrations, tests or commits because its execution surface was
  read-only. On 23 Aug 2026 the owner directed the controller to continue here;
  the controller therefore owns MNY-10A → MNY-10B → MNY-10C → MNY-11A under
  the same already-reviewed contract, consuming Lane A's exact authoritative
  hold-contract SHA. This edge deliberately prevents a second hold predicate
  even though MNY-10A has no checklist prerequisite. Migration,
  payout-model/service, worker registry, API baseline, balance and authority-doc
  edits are controller-serialized with exact leases and disjoint manifests.
  Public endpoint/schema changes and all three §9 baselines land together once
  during controlled integration. Independent package-plan review found no
  critical issue; its material invariant, ownership, contract-boundary and risk
  corrections are reconciled in the uncommitted controller ledger at
  `.codex/delivery/cardvert-pkg02/plan-ledger.md`.
- **Audit-reconciliation correction checkpoints (owner handoff, 21 Aug 2026):**
  these are controller-owned prerequisites inside the existing program, not
  new approvals or permission to reorder the queue. **PKG02-C0 (DONE with
  MNY-08C):** corrected driver explanations use corrected excluded-reason
  provenance, never original-calculation metadata. **PKG02-C1 (DONE before
  MNY-03A, MNY-10B and PKG-02 closure):** unify the DB/application clock and shared
  acceptance-versus-revision serialization; freeze the accepted campaign
  payment window in payout-v3 bindings; make populated downgrades `0018`–`0021`
  fail closed; and lock every overlapping trip row in stable order for
  adjacent-day correction projection/execution. **PKG02-C2 (before any real
  GPS/PWA authority):** enforce ADR 014 capability/session gates in the real
  tracker, recover stale writer-lock state, and retain terminal ping rejections
  as dead-letter evidence. It is registered here as a mandatory PKG-07 entry
  correction, not MNY-08C scope. **PKG02-C3 (evidence/operations):** R17-A
  proves local configuration, smoke and database restore contracts only;
  frontend-image rollback remains unexecuted and must be parameterized and
  exercised before W4-03A authority. Whole-entry payout reservation remains
  the adopted design; no broader Pro schema is admitted.
- **Closure:** every money invariant passes concurrency/property/e2e testing and
  independent money/security review.
- **MNY-08A evidence (DONE 21 Aug 2026):** migration `0022` adds exactly one
  current assessment row per sealed trip with `pending | clean | flagged |
  error`, formula/source/input fingerprints and a current-flag provenance
  watermark. The DB-derived sweep rejects stale formulas, analytics, flag sets,
  pending and error states; retry and two-worker creation converge, while
  evaluation failures persist only `assessment_evaluation_failed`. Verified:
  empty upgrade plus downgrade/re-upgrade at the single `0022` head; 60 focused
  Postgres tests including pre-existing-analytics concurrency and flag-change
  reselection; 118 focused SQLite tests (11 expected Postgres skips); ruff and
  diff checks clean. The independent money/concurrency specialist's two high
  and one medium findings were corrected in one round and rechecked RESOLVED.
- **MNY-09A evidence (DONE 21 Aug 2026):** migration `0023` adds one current,
  versioned route-replay signature per trip. Canonical absolute-payload and
  time-shift-normalized hashes detect copied routes without storing raw
  coordinates/timestamps in review evidence; same-trip retries converge and
  same-driver repetition alone does not flag. Normalized groups retain one
  latest cross-account candidate, reconcile departures and old/new transitions
  under sorted advisory locks, and use DB-side counts/latest selection,
  bounded samples and set-based cleanup. The worker sweep reselects detector,
  configuration and analytics drift; failures stay due. Verified: 165 focused
  SQLite tests (23 expected Postgres skips), 189 focused Postgres tests,
  property/scale and real pipeline coverage, concurrent reverse-order and
  old-to-new group tests, seeded-data downgrade, empty
  `0022 → 0023 → 0022 → 0023`, filtered autogenerate-empty, and ruff/diff
  clean. The independent fraud/privacy specialist's three high and three
  medium findings were corrected once and rechecked RESOLVED. Derived hashes
  are pseudonymous trip-linked location data covered by the later RM15
  retention/DSR operating model; no real-device, real-route, staging, pilot or
  user-feedback evidence is claimed.
- **MNY-08B evidence (DONE 21 Aug 2026):** migration `0024` adds the exact
  `open → acknowledged → confirmed | dismissed` staff-review lifecycle with
  coherent reviewer/time/note evidence and non-terminal per-trip/type dedup.
  One shared predicate holds `open`, `acknowledged` and `confirmed`; only
  `dismissed` releases. Review, detection, impression and payout consumers
  serialize on the same trip scope; cross-trip replay reconciliation takes an
  exclusive reader/writer gate, locks all affected trips in deterministic
  order, then takes route-fingerprint and flag-row locks. This closes the
  reviewed cross-trip stale-money race without duplicating a hold rule. Direct
  resolve and mismatched retries fail 409, exact retries converge, reviews and
  audits commit atomically, and the payout-v1 minimum floor cannot restore held
  pay. The admin console now acknowledges and resolves bounded evidence with
  terminal reviewer context. Verified: 133 focused SQLite tests (28 expected
  Postgres skips), 164 focused Postgres tests plus the corrected
  detection-versus-money and detector concurrency races, empty
  `0023 → 0024 → 0023 → 0024`, legacy fail-closed migration and conservative
  downgrade fixtures, filtered autogenerate-empty, the cross-trip
  detection-versus-money and admin-recompute-versus-worker races, 166 frontend
  tests, typecheck/lint/production build, two-project live seeded admin-review
  Playwright, API/TypeScript contract synchronization, ruff and diff checks.
  The money/concurrency specialist's sole high finding and the broader lock-order
  regression were corrected in one combined round and rechecked RESOLVED.
  Evidence is synthetic/automated;
  no real-device, real-route, staging, pilot or user-feedback claim is made.
- **MNY-08C evidence (DONE 21 Aug 2026):** migration `0025` adds one owner-only,
  idempotent dispute per fraud flag plus typed, deduplicated in-app notices.
  Driver projections expose only allowlisted reason/status/outcome fields;
  internal evidence, matched identities and review notes remain private.
  Admin replies stay separate from internal review notes, and confirmed or
  dismissed outcomes remain visible. Corrected earnings explanations take the
  eligible/excluded pair from the same newest authoritative recompute and fail
  closed on malformed provenance. Verified with focused PostgreSQL role,
  privacy, retry, atomicity and concurrent-terminal tests; 25 focused frontend
  tests; type/lint; contract drift checks; and a two-profile desktop/mobile live
  dispute→reply→reload journey. The privacy/security recheck resolved one
  combined correction round. No real-device, route, staging, pilot or
  user-feedback validation is claimed.
- **PKG02-C1 evidence (DONE 21 Aug 2026):** migration `0026` freezes nullable
  accepted campaign windows on new payout-v3 bindings; legacy provenance fails
  closed. Assignment acceptance and revision publication share one
  campaign-scoped transaction lock and PostgreSQL wall clock. Payout-v3
  calculation, staleness, correction fingerprints and persisted money metadata
  consume the frozen window, while mixed v2 corrections retain live-window
  sensitivity. Populated downgrades `0018`–`0021` and authoritative `0026`
  data fail before destructive DDL. Correction projection locks every
  overlapping trip in stable UUID order before the selected-day cap lock, then
  allocates cap chronologically. Verified: 13 focused historical migration
  cases, 11 focused terms/window cases, 8 controller-rerun migration cases,
  5 combined clock/window/race cases, nullable metadata and v3-correction
  regressions, and adjacent-day opposing-order half-cent/deadlock/stale/retry
  coverage. One specialist review's two medium evidence gaps were corrected in
  one round and rechecked RESOLVED. No API baseline or external/live claim
  changed.
- **MNY-03A evidence (DONE 21 Aug 2026, code `1f0b1f4`):** migration `0027`
  persists one review-escalation timestamp and one unique fraud-flag source for
  an available reversal. A DB-derived, starvation-safe worker sweep takes the
  existing fraud trip scope, then the post-wait database clock, and releases
  due `pending` rows only when the exact assessment inputs are
  successful-current and the imported authoritative hold predicate is false.
  Dismissal invalidates the old assessment; reassessment is required before
  release. Open/acknowledged cases escalate once at the configurable deadline
  without changing money or auto-releasing. A named confirmation after release
  posts one positive subtract-by-type reversal; retry and multiple flags cannot
  over-reverse. Verified: 21 focused PostgreSQL core cases including
  two-worker and dismissal/release races, 3 migration cycle/populated-guard
  cases, autogenerate-empty, a controller rerun of 30 integrated backend
  cases, 11 focused admin UI cases, type/lint, synchronized §9 artifacts, and
  live synthetic desktop/mobile deadline/recommendation plus named
  confirm-to-one-reversal evidence (`available_net = 0.00`, one linked ledger
  row and one audit per action). The money/concurrency specialist found one
  medium configurable-SLA UI wording defect; the single correction round was
  rechecked RESOLVED. No real-device, real-route, external-staging, pilot or
  user-feedback validation is claimed.
- **MNY-10A/B/C + MNY-11A evidence (DONE 23 Aug 2026):** migrations
  `0028`–`0031` form one linear, downgrade-guarded chain for protected payees,
  batch reservation, provider reconciliation and carry-forward debt.
  AES-256-GCM account ciphertext binds tenant/record/field AAD to a required
  versioned KEK keyring; list/error/audit/log surfaces remain redacted, while
  privileged reveal and append-only rewrap are audited. Whole-entry batch
  reservation freezes verified payee/account/amount/instruction hashes under
  maker-checker approval and one active-line constraint, consuming the imported
  fraud-hold contract. Fake-provider submission is idempotent; signed webhook
  or verified poll evidence resolves each line before `paid`, including partial
  failure and retry. Post-payment corrections and confirmed fraud append
  currency-scoped debt linked to immutable paid sources; future credit clears
  debt first and emits one exact residual. Live submission remains disabled
  until `EXT-DISBURSEMENT-PROVIDER` exists. Controlled integration regenerated
  all three §9 baselines once. Non-repeated aggregate verification recorded
  541 backend passes and one intentional skip, 187 frontend tests, typecheck,
  lint, production build, migration/autogenerate, crypto/property/concurrency
  and synthetic payee→batch→reconciliation→debt journeys. The consolidated
  review found one provider-finality/confirmed-fraud lock inversion and two
  paid-state UI color gaps; the single correction round added one shared lock
  order plus a forced-overlap PostgreSQL regression and focused UI assertions,
  then rechecked both findings RESOLVED. No live provider, physical-device,
  real-route, external-staging, pilot or user-feedback validation is claimed.
- **PKG-02 prior closure (23 Aug 2026, candidate `e3a505e`; reopened for
  correction review 24 Aug 2026):** all checklist
  items 10–18 are done; RM8/RM10/RM11 are resolved and RM9's copied-route
  software control is delivered with its physical-proof residual preserved.
  The advisory Pro register remains revalidation input at
  `docs/pro-review-register.md`, not a queue or adopted architecture. PKG-03
  had been promoted to `NEXT`; it was paused pending the correction round.
  Its controller must consume the corrected final D17 crypto seam and money
  authority without adding plaintext fallback, a second crypto subsystem or a
  second fraud-hold predicate.
- **PKG-02 correction round (DONE 24 Aug 2026, base `e8fafb4`):** one bounded
  money-authority correction now creates due reversal obligations after the
  release flush and before audit/commit in deterministic driver/currency/entry
  order; any active reservation aborts the complete release transaction.
  Undeployed migration `0031` backfills all eligible available reversals into
  one driver/currency account and obligation, links same-trip paid provenance,
  conserves totals, replays idempotently and fails before unsafe active
  reservations or populated downgrade destruction. Economic projections keep
  non-voided sources, subtract reversals and exclude `debt_remainder`; separate
  settlement fields expose released credit, cash paid, carried debt and
  batch-payable amount in both driver views and the public API. Evidence:
  focused release/idempotency/whole-entry/residual/two-trip API and PostgreSQL
  reservation-race tests; five populated migration/backfill/downgrade tests;
  contract baselines moved together; frontend 191 tests, typecheck, lint
  (one pre-existing warning) and production build; full backend aggregate
  `793 passed, 3 skipped` before 13 documentation-contract fixture failures,
  all repaired and rechecked by `41 passed`; final clean-context
  minimal-change review PASS (one packaging reminder satisfied). No live
  provider, physical-device, real-route, external-staging, pilot or
  user-feedback validation is claimed. PKG-03 is promoted but not started.
- **Closure-CI fixture correction (24 Aug 2026):** the first closure run passed
  797 backend tests before six production-Compose missing-secret assertions all
  stopped at the newly required payout keyring. `staging.env.example` now
  supplies an explicit synthetic render-only keyring and the missing-value
  matrix covers it; the static verifier also supplies that explicit env file to
  both Compose renders. All 26 pre-production operations tests pass. This adds
  no runtime fallback and changes no Package 2 behavior.

### PKG-03 — commercial contracts and billing

- **Owns:** checklist 19–27. Commercial terms, receipts, invoices, funding,
  payment adapters, corrections and budgets share one canonical money model.
- **Package plan (activated 24 Aug 2026, canonical branch `feat/pkg-03`):**
  the controller serializes W2-00A → W2-00D → W2-00B → W2-01A → W2-01B →
  W2-00C → W2-01C → W2-01D → W2-01E under one campaign/commercial lock
  order and a migration chain beginning after `0031`. Domain work stays behind
  one controlled public-contract integration that moves all three §9 baselines
  in the same commit and reruns the required R14-B fixtures. The controller is
  the only implementation, migration, contract and authority-document writer;
  read-only specialists review the money/tax/concurrency/provider checkpoints.
  Provider-neutral W2-01C and policy-neutral W2-01E seams may build; missing
  provider credentials and production budget values gate live use, not that
  synthetic/configurable implementation. The complete plan
  received one clean-context plan review; all material post-build corrections
  are committed in `f347b37` and `8272b32`, with deterministic browser evidence
  finalized in `86d9934` and a final no-history consolidated review PASS. The
  later Extended-Pro correction range from `a8fa4e0` was implemented in
  `d146140`: receipt/start chronology, allocation-scoped refund conservation,
  correction retry identity, rendered-prefix invoice numbering and
  campaign/terms currency serialization received one consolidated no-history
  review, one focused race correction and final PASS.
- **Closure (24 Aug 2026):** migration head
  `0042_invoice_number_prefix_sequence`; the original 874-backend/193-frontend
  package baseline plus focused PostgreSQL reversal/start, refund, retry,
  numbering, migration and currency-race evidence pass. The single correction
  aggregate exposed only three historical migration/seed harness expectations;
  those were isolated at their owning revisions, corrected and rerun green.
  Ruff, contract drift, lint/typecheck, 193 frontend tests, production build and
  8 fresh-head isolated desktop/mobile billing journeys pass; the final
  independent review verdict is PASS. W2-01C remains
  `BLOCKED — EXT-PAYMENT-PROVIDER`; W2-01E is now complete under a
  configurable/provider-neutral contract. Issuer, production budget policy and
  real commercial values remain fail-closed live-use gates.
- **Owner build-entry correction (26 Aug 2026):** W2-01E was incorrectly
  represented as impossible to build while `EXT-BUDGET-POLICY` is missing.
  The missing live values remain MISSING and cannot be invented, but they do
  not prevent configurable/provider-neutral implementation.
- **W2-01E checkpoint evidence (26 Aug 2026):** migration `0064` expands the
  append-only budget record with policy/revision/source identity, advertiser
  billing-fact basis, thresholds, alert/pause/resume authority and immutable
  campaign transitions. Confirmed unreversed allocations, or the production
  obligation after actual start, are the only spend inputs; payout/driver cost
  is absent. Receipt allocation, reversal, evaluation, pause and audited admin
  resume share one campaign lock order. Exact retries reuse evaluations,
  transitions and outbox keys. Default production configuration persists only
  `EXT-BUDGET-POLICY` blocked evidence; explicit synthetic test policy drives
  alert/pause/reversal/resume tests. Real PostgreSQL migration, autogenerate and
  funding-versus-worker race checks pass. `EXT-BUDGET-POLICY` remains MISSING
  and no live threshold or approval is claimed. With W2-01C still externally
  blocked, PKG-03 has no runnable unfinished row.

### PKG-04 — secure evidence, activation and communications

- **Owns:** checklist 28–43, with internal checkpoints for storage/security,
  KYC lifecycle, approvals/activation/cancellation, then communications.
- **Package plan (activated 24 Aug 2026, canonical branch `feat/pkg-04`):**
  adopt verified shared CI repair `a8fa4e0`, then serialize Package 4 behind one
  controller-owned migration/contract/authority boundary. W2-03A is the sole
  admitted first slice: dedicated submit/approve/reject/resubmit transitions
  bind immutable reviewed campaign snapshots and cannot schedule or activate.
  One no-history Terra worker owns bounded domain/API/UI/test implementation;
  the controller owns migrations, all three §9 baselines and authority docs,
  with one independent plan review PASS before implementation. Focused tests
  only at that checkpoint. Corrected Package 3 tip `878be3a` was integrated by
  merge commit `5866dca`, preserving both histories; governance commit
  `e4533a9` was then adopted. W2-04A was admitted next and is now complete.
- **Build-first authority correction (26 Aug 2026):** the project owner
  confirmed that the already-requested production accounts, credentials,
  provider selections and legal/real-world evidence gate live use and the
  pilot, not provider-neutral/local/synthetic implementation. Consistent with
  D23 and the external-register rule, W2-02A/B/D and W2-04B/D return to `TODO`;
  their production adoption and live delivery remain fail closed while the
  corresponding external IDs stay `MISSING`. Package 4 is the sole active
  package and resumes at W2-02A without changing any client fact.
- **W2-02A checkpoint evidence (26 Aug 2026):** migration `0052` adds tenant-
  owned upload intents and private managed stored-file authority after the
  published `0051` head. One S3-compatible storage port and local MinIO adapter
  issue short-lived, exact type/size/checksum-bound presigned POSTs; confirmation
  streams and hashes the server object, promotes it idempotently from the
  lifecycle-managed `unconfirmed/` prefix, and returns no bucket, URL or storage
  key. Missing configuration and provider outages fail closed before a new
  intent persists. A bounded worker purge removes abandoned source or partially
  promoted objects, while populated downgrade refuses destructive loss. Eight
  focused API/service cases, the populated migration round trip, worker and
  migration-head and audit-route controls, 68 combined focused checks, Ruff,
  Compose parsing,
  synchronized §9 artifacts and a real private MinIO POST→verify→promote flow
  pass; the unsigned GET returned 403. The independently challenged Package 4
  plan covered tenant, replay, outage, promotion, lifecycle and migration-loss
  boundaries; the consolidated post-build security review remains reserved for
  the shared W2-02 boundary. `EXT-STORAGE-PROVIDER` remains MISSING and no
  client account, production provider, credential or live upload is claimed.
- **W2-02B checkpoint evidence (26 Aug 2026):** additive migration `0053`
  records actual MIME, attempts, retry timing, terminal scan time and sanitized
  unsafe/error state on the one stored-file authority. A provider-neutral
  streaming scanner port and local ClamAV INSTREAM adapter recount bytes and
  magic-sniff the allowed formats independently of client metadata; pending,
  unavailable, missing, spoofed, changed-size, infected and rejected files all
  remain quarantined. The bounded worker row-locks/rechecks candidates and
  commits exponential retry state without duplicate terminal scans. Only exact
  clean files receive at-most-60-second private GETs, with advertiser/admin
  role-purpose restrictions, tenant hiding, active-admin service authorization
  and one audit containing actor, file, purpose, reason and request ID. The
  initial missing-module/migration collection failures provide red evidence;
  80 combined focused API/service/worker/protocol/migration/head/audit/contract
  controls, Ruff and Compose parsing pass green. An isolated populated
  PostgreSQL upgrade/downgrade proves the `rejected` constraint transition and
  fail-closed downgrade mapping. A real local clamd daemon
  returned `clean` for benign bytes and `Eicar-Test-Signature` for the standard
  harmless antivirus test string; the real MinIO adapter returned the exact
  body through a 60-second signed GET while the unsigned GET remained 403.
  `EXT-MALWARE-SCANNER` remains MISSING; the
  official local image runs under explicit amd64 emulation on ARM hosts and no
  production scanner, credential, live file or provider validation is claimed.
- **W2-02C checkpoint evidence (26 Aug 2026):** migration `0054` preserves
  readable legacy URL creatives while adding one unique restrictive managed-
  file binding for new writes and blocking destructive downgrade when such
  bindings exist. Campaign/file locks, tenant and purpose scope, exact clean-
  scan state and server-derived MIME/checksum make identical retries converge,
  changed reuse conflict, pending/infected/cross-tenant/URL-only writes fail
  closed and advertiser `ready` claims reject. Creative reads identify managed
  versus legacy sources; offer construction independently rejects legacy or
  changed/non-clean authority without implementing the W2-03B approval gate.
  The browser hashes locally, uses same-origin session BFF routes to obtain and
  confirm an exact private POST, uploads directly to storage, polls scan state
  with actionable retry/error copy, and submits only the cleared file ID.
  Initial missing-migration collection failure provides red evidence; 73
  focused backend/API/offer/migration/head/contract checks, 12 focused frontend
  schema/action/BFF/upload checks, Ruff, typecheck, lint and the production
  frontend build pass. Isolated PostgreSQL proofs confirm populated upgrade/
  downgrade and concurrent same-file convergence; the pre-existing assignment
  race test also passed on focused retry after one transient local database
  connection timeout. A real isolated MinIO→ClamAV→creative flow passed and its
  temporary containers/network were removed. `EXT-STORAGE-PROVIDER` and
  `EXT-MALWARE-SCANNER` remain MISSING; no production provider, creative
  approval, live upload, external staging or pilot validation is claimed.
- **W2-02D checkpoint evidence (26 Aug 2026):** migration `0055` extends the
  single stored-file authority with mutually exclusive organization/driver
  scope and adds immutable versioned driver-KYC and vehicle-evidence records.
  Required clean, purpose-matched, subject-owned licence/photo/agreement and
  registration/insurance/photo files bind to those versions; verified bank
  versions are rechecked against the same driver payee. NIN is never a
  plaintext column or list response: it reuses D17's exact envelope mapping and
  tenant/record/field AAD, exposes only last-four masking, and requires an
  active-admin purpose plus atomic redacted audit for reveal. The unchanged
  application crypto port now delegates KEK wrapping to an adapter-private
  custody backend; local/test keyrings remain available while a production
  KMS/vault can replace custody without changing ciphertext. Rewrap appends one
  KYC version under the stable identity record, preserves data ciphertext and
  converges on the active key. Exact request retries converge; changed retries,
  cross-driver bank/file substitution, uncleared files, tampered AAD/ciphertext
  and missing custody fail closed. An observed temporary scan-gate mutation
  failed before the restored invariant passed. One hundred fifteen focused
  crypto/payee/file/scanner/KYC/migration/creative/audit/contract checks pass
  with ten environment skips; real PostgreSQL proves the full `0001→0055`
  empty round trip, populated downgrade refusal and concurrent retry/version
  serialization.
  Frontend typecheck/lint/build and synchronized §9 contracts pass, as does a
  real isolated three-file MinIO→ClamAV→encrypted-KYC flow; its temporary
  services/network were removed. `EXT-KMS-CUSTODY` remains MISSING. W3-04B/C
  still own person/payee and vehicle approval/work eligibility; no production
  custodian/provider, live identity check, approval or pilot evidence is
  claimed.
- **W2-02E checkpoint evidence (26 Aug 2026):** optional positive
  `FILE_KYC_RETENTION_DAYS` has no production default; absent policy disables
  the worker and rejects execution while the active-admin API still supports
  an audited readiness dry-run. Rejected/expired KYC and vehicle-evidence
  versions purge under one PostgreSQL advisory lock; stable locks and reference
  rechecks preserve pending/approved and shared KYC/creative files, while
  private object deletion precedes row removal and remains idempotently
  retryable after first-, mid-batch- or concurrent-provider failure. Every
  submission/file/completed-run audit is redacted. Scanner outage, storage
  outage and key-loss paths remain fail closed, and the operations runbook
  records bounded recovery without inventing a provider, custodian or legal
  value. Session refresh, driver self-profile update and assignment accept/
  decline/deactivate now audit atomically; identical assignment retries create
  no second decision audit, leaving no `KNOWN_UNAUDITED` mutating route. The
  initial missing lifecycle module was observed red. A broad focused run
  reached 210 passed/1 expected environment skip and exposed one misplaced
  test-only assertion; its two-case correction and the final 20-check changed-
  boundary gate pass. Ruff, Compose parsing, byte-stable regenerated §9
  contracts, frontend type/lint/build, real PostgreSQL concurrent-purge proof,
  and a real private MinIO→ClamAV→encrypted-KYC→dry-run→object purge flow pass;
  the disposable local services were removed. There is no migration in this
  checkpoint. `EXT-LEGAL-PRIVACY`, `EXT-STORAGE-PROVIDER`,
  `EXT-MALWARE-SCANNER` and `EXT-KMS-CUSTODY` remain MISSING and no live
  retention, provider, identity, approval or pilot validation is claimed.
- **W2-03A checkpoint evidence (24 Aug 2026):** migration `0043` extends the campaign
  lifecycle and adds append-only, exact-submission-bound review evidence.
  Dedicated row-locked advertiser/admin actions enforce submit, approve,
  reasoned reject and resubmit; generic creation/update cannot bypass review,
  and approval cannot schedule or activate. Advertiser detail/history and the
  typed `/admin/approvals` queue expose the same snapshot digest and immutable
  transition history. Focused evidence: 19 backend passes plus 13 expected
  SQLite skips, 5 PostgreSQL lifecycle/race/migration passes, filtered
  autogenerate-empty, 4 OpenAPI/migration-chain passes, 18 frontend tests,
  55 R14-B fixtures, typecheck and lint (one existing compiler warning), and
  the isolated real-stack submit→approve→history journey in desktop/mobile
  Chromium (2 passes). All three §9 baselines moved together. No provider,
  scheduling, activation, physical-device, real-route, staging, pilot or
  user-feedback validation is claimed.
- **W2-03B checkpoint evidence (26 Aug 2026):** migration `0056` adds the
  `draft | rejected → pending_review → approved | rejected` managed-creative
  lifecycle and append-only, exact-submission-bound snapshot evidence without
  removing readable legacy `ready` rows. Advertisers cannot write review
  states; pending/approved definitions are frozen, rejected definitions can be
  corrected and resubmitted, and approval rechecks the tenant-owned exact clean
  file under campaign→creative→file locks. The combined approvals page exposes
  campaign and creative queues, reasoned decisions and immutable history, while
  the advertiser campaign page submits reviewable creatives. Offer creation
  and activation now require `approved`; legacy `ready`, rejected, replaced or
  newly unsafe assets fail closed. An initial two-endpoint 404 red run preceded
  the implementation; a resubmission regression then exposed and corrected a
  same-second event-order bug by selecting the one undecided submission.
  Fifty-nine focused campaign/creative/assignment/audit checks pass with ten
  expected environment skips, as do the real PostgreSQL opposite-decision race,
  two populated migration round-trip/append-only checks, six contract/audit
  checks with one expected skip, Ruff, 12 frontend approval/action checks,
  typecheck, lint and the production frontend build. Regenerated §9 contracts
  are byte-stable. W2-02C's real local MinIO→ClamAV foundation remains the file
  boundary; this checkpoint adds no production provider or live approval claim.
- **W2-03C checkpoint evidence (26 Aug 2026):** migration `0057` extends the
  shared subject-scoped file authority with immutable assignment/vehicle/
  driver/device-bound installation revisions, admin review, one-use hashed
  server-nonce challenges and fresh display proofs. Exact configured views and
  clean scanned images are rechecked at submission and approval; changed
  retries, cross-driver files, stale approval, device mismatch, pre-challenge
  photos and nonce replay fail closed. Trip start requires and stores the exact
  current proof. Driver capture/proof actions and the combined admin approvals
  queue use same-origin BFFs and audited, purpose-scoped photo reads. Uploader,
  view, renewal and challenge/proof windows have no production defaults; absent
  policy remains visibly unavailable under `EXT-EVIDENCE-POLICY`. The initial
  route 404 and absent-policy 503 were observed before the implementation.
  Thirty-three focused evidence/file/trip/migration checks pass; real
  PostgreSQL proves one winner under concurrent nonce consumption and populated
  migration round trips/append-only guards. Eight audit/OpenAPI checks and 11
  focused frontend tests pass with typecheck, lint and a production build; §9
  contracts are synchronized. W2-03D still owns atomic activation and W2-03G
  owns missed/periodic challenges and spot checks. No production policy,
  physical-device, real-route, live-staging, launch, earning or pilot evidence
  is claimed.
- **W2-03D checkpoint evidence (26 Aug 2026):** the existing named admin
  activation command now holds the shared commercial-authority lock and stable
  campaign→assignment→driver→vehicle rows while rechecking campaign review,
  current accepted creative/offer/binding, funded liability reserve, valid
  production and new-work authority, approved installation evidence and vehicle
  exclusivity. The status change, timestamp, audit and canonical digest-bound
  activation snapshot share one transaction and the existing append-only
  activation-event authority; exact active retries recheck current gates and
  converge without another event. Trip start requires the snapshot and still
  independently rechecks current financial authority and display proof. The
  pre-build all-gates regression returned the prior 409 placeholder, then
  passed after implementation; a real synthetic admin activation→driver trip
  flow passes. Real PostgreSQL proves activation commits before a waiting cash
  reversal cutoff, after which new work fails closed, and preserves existing
  cancel/deactivate/trip serialization. No migration or §9 shape change was
  required. This is provider-neutral build evidence only: no live funding,
  production start, installation approval, route, earning or pilot claim.
- **W2-03E checkpoint evidence (26 Aug 2026):** migration `0058` adds governed
  campaign-change requests and append-only effective revisions with stable
  retry identity, immutable before/after impact and explicit expansion,
  reduction and date-change classification. Expansions apply only under the
  shared campaign authority when funded headroom covers all assignment and
  change liability; insufficient funding waits visibly. Reductions, removals
  and every date change require a reasoned admin decision, while retroactive
  dates and changed retries fail closed. Accepted assignment bindings remain
  immutable, interval reads resolve the revision then in force, and reasoned
  assignment removal preserves its event history. PostgreSQL proves exact
  approval retries, funding-versus-change serialization, reservation
  conservation, tenant isolation, populated migration guards and append-only
  enforcement. Focused campaign/change/assignment/migration/audit, billing and
  OpenAPI checks pass, as do 86 frontend and preserved R14-B tests, Ruff,
  type/lint/build and byte-stable regenerated §9 contracts. An isolated
  synthetic advertiser expansion→admin-approved reduction browser journey
  passes; its disposable database was removed. No live funding, production
  change, approval, route, earning or pilot evidence is claimed.
- **W2-03F checkpoint evidence (26 Aug 2026):** migration `0059` adds one
  append-only advertiser cancellation and settlement-revision authority plus a
  terminal liability-release transition. The exact-retry command holds the
  shared campaign lock, records one database-time cutoff, cancels nonterminal
  assignments without rewriting accepted/event history, releases reserved
  liability and classifies cash-refund, closed-window, credit-settlement or
  no-settlement outcomes from existing W2-01D evidence. Trip start, ingestion,
  analytics, payout-v2/v3 and day recompute share the cutoff chronology;
  post-cutoff pings remain evidence but cannot earn. Exact standard-boundary,
  tenant/retry, populated migration, append-only, release-terminal and
  cancel-versus-trip races pass. A temporary missing-cutoff mutation made both
  payout engines overpay and the restored implementation passed. Nineteen
  focused migration/API/audit/contract checks, 17 adjacent money/trip checks,
  11 frontend tests, type/lint/build, byte-stable §9 artifacts and one isolated
  real browser cancellation journey pass; its database was removed. No refund
  transfer, live funding, provider, route, earning or pilot evidence is claimed.
- **W2-03G checkpoint evidence (26 Aug 2026):** migration `0060` adds one
  assignment/trip-bound verification queue for configurable high-earner
  display-proof renewal, concurrent-session evidence and reasoned physical
  spot checks. Exact worker/admin retries serialize, a fresh nonce proof
  satisfies pending renewal work before its exact deadline, and missed,
  overlapping or failed checks create the existing MNY-08B fraud flag rather
  than a second hold authority. Acknowledgement/confirmation/dismissal and
  money release remain owned by that state machine. Missing high-earner policy
  is reported without inventing production values, tenant reads stay scoped,
  and every stored/displayed boundary says phone GPS is not proof that the
  branded vehicle moved. A reversed deadline predicate produced the expected
  red pending challenge; the restored flow passed. Thirty focused PostgreSQL
  worker/race/migration/API/audit/contract checks and 94 configuration checks
  pass, as do 13 frontend tests, typecheck, scoped lint, production build,
  byte-stable §9 artifacts and an isolated real ops queue→failed-check→fraud-
  hold browser journey. No live policy, physical inspection, GPS, earning,
  provider, staging or pilot evidence is claimed.
- **Corrected-authority seam evidence (24 Aug 2026):** Package 4 migration
  `0043` now descends from Package 3 head `0042`. The adopted Package 3
  campaign/terms currency lock initially exposed one stale-update ordering
  against review submission; the tenant campaign row is now locked before the
  review-state check while retaining advisory-lock-first currency ordering.
  The barrier proves the stale loser returns
  `CAMPAIGN_REVIEW_STATE_CONFLICT` and live/snapshotted currency remain equal.
  Six focused PostgreSQL authority/review cases, six migration/OpenAPI checks,
  filtered autogenerate, 40 delivery-control cases, Ruff and 55 R14-B fixtures
  pass. W2-03A remains complete; no Package 3 full-suite rerun was performed.
- **W2-04A checkpoint evidence (24 Aug 2026):** migration `0044` converts the
  MNY-08C fraud-notice foundation into a recipient/channel-scoped outbox with
  exact retry fingerprints, unique provider receipt identity, immutable
  evidence, delivery/read state, an unread index and lossless legacy backfill.
  Current-user APIs and same-origin BFF routes expose sanitized list/unread/
  read operations; one root TanStack Query provider mounts a visible-only
  45-second polled centre for admin, advertiser and driver. D24's default-on
  advertiser-organization email preference is shared, manager-controlled and
  audited; in-app remains mandatory. All three §9 baselines moved together.
  Focused evidence: 22 backend passes with 5 expected environment skips; 6
  real-PostgreSQL feed/migration/autogenerate passes; 4 OpenAPI/contract passes;
  62 frontend and preserved R14-B fixtures; typecheck, scoped lint and Ruff;
  and 8 isolated real-stack desktop/mobile three-role Playwright passes.
  Consolidated independent review passed after correcting fresh in-app `sent`
  semantics and provider-ID uniqueness. No email provider, driver WhatsApp/
  SMS, push, external/live-provider, physical-device, staging, pilot or user-
  feedback validation is claimed. Remaining Package 4 work is dependency-
  blocked, so the executable frontier advances to PKG-05/W3-00A without
  starting it in this checkpoint.
- **W2-04B checkpoint evidence (26 Aug 2026):** migration `0061` adds bounded
  email-dispatch claims, exponential retry timing and immutable, uniquely
  keyed terminal receipt evidence over the existing outbox. The worker
  rechecks active advertiser membership and the organization preference before
  every send, uses one notification ID as the provider idempotency key, and
  recovers expired claims without duplicate concurrent dispatch. Typed code
  templates and a provider-neutral SMTP port run against local Mailpit; blank
  or partial production configuration remains fail closed. Canonical HMAC
  receipts require the configured key ID, converge on exact replay, reject
  changed or contradictory terminal events and update only the uniquely
  matched provider message. A reversed preference predicate produced the
  expected red send and the restored guard passed. Seven focused delivery/
  preference/concurrency/receipt cases, two PostgreSQL migration round trips,
  156 combined notification/config/worker/contract/control checks, 42 preserved
  R14-B/frontend fixtures, typecheck, Ruff, synchronized byte-stable §9
  artifacts and a real local SMTP send plus signed 200/200/401 receipt flow
  pass. `EXT-EMAIL-PROVIDER` remains MISSING; no production
  provider, verified sender, live recipient or delivery claim is made.
- **Package 4 post-review correction evidence (24 Aug 2026):** Extended Pro's
  exact-head review found three uncovered authority defects plus stale PR
  controls. Generic campaign PATCH now treats only an identical status as a
  no-op and rejects every lifecycle change; campaign-zone create/update/delete
  lock the campaign before mutability checks and writes; external-channel
  notification rows start `pending` with no sent timestamp while in-app rows
  start `sent`. Audit, migration/seed-head and Package 3 fixtures now follow the
  governed review path, and notification E2E creates idempotent per-role data
  with one serialized preference mutation. Focused evidence: 83 backend passes,
  including six PostgreSQL submission-versus-zone races; a controller rerun of
  the affected controls passed 64 with 25 environment skips; Ruff, frontend
  lint/type and diff checks pass; the corrected real-stack desktop/mobile
  notification journey passes 7 with one intentional mobile preference skip.
  External provider deferrals remain unchanged and no live delivery is claimed.
- **W2-04C/D closure evidence (26 Aug 2026):** authoritative assignment,
  campaign approval, funding, budget, cancellation, evidence, fraud and payout
  transitions now write typed stable-key notices into the existing outbox.
  Driver WhatsApp/voice remains a consent-bound manual operations task whose
  completion explicitly makes no provider-delivery claim. Advertiser/admin
  recovery is non-enumerating, rate-serialized, expiring and single-use;
  completion increments session authority. Driver phone fingerprints and
  challenge codes are keyed hashes, the challenge work queue exposes only a
  mask, live send recording requires the external gate plus opaque provider
  evidence, and versioned consent is withdrawn on phone change. Production
  reset delivery also fails before provider submission without a public reset
  URL. Focused red/green mutations caught missing billing spend and missing
  session revocation. Real PostgreSQL migration/append-only/autogenerate and
  concurrent reset/funding races pass; the relevant backend aggregate, typed
  frontend contracts and preserved R14-B fixtures pass. All three §9 artifacts
  regenerate byte-stably. `EXT-EMAIL-PROVIDER` and `EXT-PHONE-OPERATOR` remain
  MISSING; no live provider delivery or operator account is claimed.
- **Closure:** PKG-04 is DONE. All owned checklist rows 28–43 have verified
  implementation evidence; provider/custody/legal live-use gates remain in the
  external register and do not reopen the package.

### PKG-05 — privacy, measurement and retargeting

- **Owns:** checklist 44–54. The privacy operating model, disclosure service,
  measurement runs, sources, segments, recommendations and scores are one chain.
- **Package plan (activated 24 Aug 2026, canonical branch `feat/pkg-05`):**
  the controller serializes the dependency-safe frontier W3-00A → W3-00D →
  W3-00C → W3-01A → W3-01B and owns all authority, migration, disclosure,
  public-contract and control-plane surfaces. The later build-first correction
  completed W2-02E and W2-03C/D, making W3-00B and W3-00E runnable without
  changing their live legal/methodology gates. The client input document proves the legal,
  report-method and ad-platform facts were requested, not supplied, so
  `EXT-LEGAL-PRIVACY`, `EXT-REPORT-METHOD` and `EXT-AD-PLATFORM` remain
  MISSING and live use defaults denied. One clean-context Terra plan review
  returned FIX; its full endpoint-inventory/live-gate, atomic differencing,
  synthetic-ROI, source/link history/concurrency and migration corrections
  were reconciled, and the same reviewer returned PASS. The bounded plan and
  review record live at `.codex/delivery/cardvert-pkg05/plan-ledger.md`.
- **W3-00A checkpoint evidence (24 Aug 2026):** a machine-checkable privacy
  register and operating model now cover nine purposes/data classes with
  organizational ownership, explicitly unapproved candidate lawful bases,
  retention dispositions, recipients, controller/processor allocation,
  notice/withdrawal rules, subprocessors/regions, breach responsibilities and
  seven DPIA risk classes. Every named owner, legal basis, notice, retention/
  DSR decision, provider, region and notification rule remains MISSING;
  `live_use_authorized=false`. A deterministic synthetic withdrawal and raw-
  route-breach tabletop stops at the exact W3-00B, Package 4 and legal gates.
  Focused evidence: 43 privacy/control tests, progress validation, JSON parse,
  Ruff and diff checks pass. The independent privacy specialist's sole finding
  removed staff from raw-location recipients; the corrected service-only
  analytics/fraud/payout plus grandfathered-heatmap boundary is test-pinned and
  rechecked PASS. No real person, GPS, KYC, provider, notification, legal
  approval, DSR execution, advertiser output or live-use evidence is claimed.
- **W3-00D checkpoint evidence (24 Aug 2026):** the machine-checkable
  measurement contract now maps every current advertiser-visible measure to
  its class, unit, provenance, vintage, missing-data rule and uncertainty
  treatment. The internal `estimated_impressions` field is presented as
  **Modelled potential contacts**; the default title is **Campaign Performance
  Analysis**; attribution/view/reach/exposure overclaims were removed from the
  current advertiser copy. Target-area coverage has a visibly synthetic-only
  candidate numerator/denominator and keeps its live qualifying rule MISSING.
  Production ROI defaults omitted and requires all advertiser conversion/
  revenue, approved method, attribution, cost, currency, time, exclusion,
  correction, provenance and immutable-manifest prerequisites. Its sole
  enabled golden is `test_only` synthetic evidence, not approval;
  `EXT-REPORT-METHOD` remains MISSING. Focused evidence: four methodology/
  copy tests, frontend typecheck, 210 frontend tests, formatting and diff
  checks pass. Independent measurement/legal/commercial review found one
  unlabeled confidence diagnostic; all visible instances now disclaim
  statistical-interval meaning and the reviewer rechecked PASS. No report was
  issued and no live or client methodology fact is claimed.
- **W3-00C checkpoint evidence (24 Aug 2026):** migration `0045` and the
  central service boundary now cover all eight current advertiser/report/
  heatmap outputs. The production gate runs before membership, data or history
  reads and requires non-placeholder legal, disclosure-configuration and
  retention references; numeric thresholds alone cannot enable it. Reports
  remain additionally denied until W3-00E safe runs. The grandfathered
  heatmap reader now releases only coarse cells meeting distinct vehicle,
  trip and day floors plus one contributor cap applied to every serialized
  ping, trip, distance and impression metric. Atomic history
  binds principal, tenant, campaign, endpoint, window, filters and result
  fingerprint; one global spatial-history lock plus hierarchical global/org/
  campaign overlap checks prevents cross-endpoint, cross-principal,
  complementary and changed-result differencing. A daily DB-time worker purge
  physically enforces configured history expiry, and populated downgrade
  refuses destructive loss. Synthetic-only settings are impossible outside
  `environment=test`; all live flags/references remain false/blank while
  `EXT-LEGAL-PRIVACY` is MISSING. Focused PostgreSQL evidence covers exact/
  below thresholds, ties, empty/sticky suppression, sequential and concurrent
  overlap in both parent/child orders, all-route no-read/no-write denial,
  tenant/RBAC, migration round-trip/downgrade and autogenerate-empty. Existing
  report/impression/heatmap and Compose checks pass. Independent privacy/
  security/architecture review found and rechecked fixes for hierarchical
  overlap and guaranteed no-traffic retention, returning PASS. No new raw-
  ping reader, report issuance, real data, approved threshold or live output
  is claimed.
- **W3-01A checkpoint evidence (24 Aug 2026):** migration `0046` adds an
  advertiser-organization source projection, append-only lifecycle evidence
  and actor/operation-scoped retry authority for exactly the five D11 planning
  source kinds. Positive discriminated schemas expose only aggregate category,
  channel, stage, bounded-window/count-band and confidence-band facts plus
  candidate provenance, unapproved basis/notice state, expiry and DSR role/
  status; identifiers, URLs, uploads, notes, opaque metadata and unknown/nested
  fields reject. The central privacy gate runs before every advertiser/admin
  read or mutation, active organization membership is service-enforced, and
  corrections are deactivate-plus-new rather than mutable updates. Exact and
  concurrent same-key retries converge under an advisory transaction lock;
  changed payload reuse conflicts. Source/event snapshots share one closed
  public contract, history is trigger-protected, expiry is DB-time derived,
  and populated downgrade refuses loss. Advertiser management and read-only
  admin monitoring role surfaces move with all three §9 baselines. Focused
  API/RBAC/lifecycle/expiry/retry/contract tests, frontend type/lint, Ruff and
  generated-contract checks pass; the PostgreSQL race/migration tests are
  present and skip only when the optional test database is unavailable.
  Independent privacy/security review found the initially open response
  dictionary and missing concurrent proof; both were corrected and rechecked
  PASS. `EXT-LEGAL-PRIVACY` remains MISSING; no approved lawful basis, real
  audience, upload, identity, raw-ping join or live source use is claimed.
- **W3-01B checkpoint evidence (25 Aug 2026):** migration `0047` adds one
  advertiser-organization source/campaign/target-zone/time linkage projection,
  append-only create/remove evidence and actor/operation-scoped retry records.
  The service locks source → campaign → zone → link, rechecks active tenant,
  source expiry, campaign bounds and zone ownership, freezes typed snapshots
  and parent fingerprints, and reports later parent changes as stale without
  rewriting history. The privacy gate precedes advertiser and service-enforced
  active-admin access; cross-tenant, inactive, expired and changed-payload
  operations fail closed. Advertiser setup/removal and read-only admin
  monitoring is service-authorized for active admins and moves with all three
  §9 baselines. Focused API/RBAC/lifecycle/
  retry/audit/migration/frontend checks pass; five real-PostgreSQL migration/
  concurrency cases cover 0045–0047, same- and distinct-key retries plus
  source-deactivation and campaign/zone races.
  The independent privacy/authorization review's service-admin and parent-race
  findings were corrected and rechecked PASS. Aggregate evidence: 722 backend
  passes with 244 environment skips after three stale Package 5 expectations
  were corrected and focused-rechecked; 212 frontend tests, typecheck, lint
  (one pre-existing warning) and a successful webpack production build.
  `EXT-LEGAL-PRIVACY`, `EXT-REPORT-METHOD` and
  `EXT-AD-PLATFORM` remain MISSING; no raw-ping join, person-level audience,
  report issuance, export, live source use or platform activation is claimed.
- **W3-01C checkpoint evidence (26 Aug 2026):** migration `0065` adds
  append-only exposure-segment versions and disclosure-cleared coverage-cell/
  time/context rows bound to one immutable measurement run and one current
  organization/campaign/target-zone source link. The worker accepts one closed
  aggregate-only schema, rejects identifier/free-form fields, applies the
  central distinct-vehicle floor before persistence, stores only releasable
  cells, fingerprints all facts and returns exact retries while changed facts
  create a linked reissue. A per-link PostgreSQL transaction lock serializes
  concurrent workers; parent fingerprint drift is surfaced as stale without
  rewriting issued history. The combined W3-01C gate passed 71 tests on real
  PostGIS, including measurement/source/link/materialization races; clean
  `0065` upgrade, empty downgrade and re-upgrade passed. Focused suppression
  red/green passed through a temporary threshold-bypass mutation. The
  controller-authorized execution-only task omitted an additional reviewer
  cycle. `EXT-LEGAL-PRIVACY` and `EXT-AD-PLATFORM` remain MISSING; synthetic
  materialization is verified; live activation remains disabled.
- **W3-01D checkpoint evidence (26 Aug 2026):** migration `0066` and one
  governed delivery authority derive deterministic geography/time/context
  recommendations, controlled CSV output and synthetic activation from the
  same issued W3-01C aggregate. Immutable receipts bind provenance,
  disclaimer, measurement uncertainty and the closed outbound payload;
  tenant/campaign authorization, current disclosure suppression and stale or
  empty parents fail closed before delivery. The outbound schema rejects
  identifier, route/ping and person-level fields before adapter invocation.
  PostgreSQL locks and immutable request fingerprints make retries converge,
  changed facts conflict and concurrent activation serialize. Focused backend,
  migration, OpenAPI and route-audit checks passed 19 tests; frontend and
  preserved R14-B fixtures passed 90 tests, with Ruff, typecheck, scoped lint,
  formatting and the production build green. Advertiser recommendations/CSV
  and read-only admin monitoring move with all three synchronized contract
  baselines. `EXT-AD-PLATFORM` and `EXT-LEGAL-PRIVACY` remain MISSING: the fake
  adapter is verified, while live platform activation remains disabled and no
  credentials, budget or legal approval is claimed.
- **W3-02A checkpoint evidence (27 Aug 2026):** migration `0067` records
  immutable `exposure_v1` campaign/route scores bound to one issued measurement
  run, frozen proof/input hashes and a canonical formula fingerprint. Route
  scores combine capped distance and active-tracking components with frozen
  quality; campaign scores use an active-time-weighted route mean, half-up to
  two decimals on a 0–100-point scale. Missing computable routes produce an
  explicit insufficient-data result instead of a fabricated number. Exact
  retries converge, changed inputs create linked immutable history, unsupported
  formula versions conflict and previously issued results never rescore.
  Advertiser reporting labels the score as an uncalibrated operational index,
  explicitly separate from impressions, potential contacts, attribution and
  ROI. Focused backend/API checks passed 11 tests with two environment skips;
  the real-PostgreSQL migration/concurrency/version gate passed 10 tests, the
  adjacent methodology/disclosure/segment seam passed 28, and frontend
  terminology, typecheck, scoped lint, formatting and build passed. All three
  §9 contract baselines moved together. No live methodology approval,
  calibration corpus, ROI input or external fact is claimed.
- **W3-02B checkpoint evidence (27 Aug 2026):** `high_exposure_zone_v1`
  ranks frozen disclosure-cleared segment facts by modelled potential contacts,
  trip count and stable zone UUID tie-break, preserving formula, score and
  measurement provenance from immutable history. Suppressed, stale,
  unavailable and cross-tenant inputs expose no ranked item, label, geometry
  metadata, count or provenance. Admin monitoring and advertiser map/report
  surfaces use one reusable governed component and continue to distinguish the
  exposure score from impressions, contacts, attribution and ROI. Focused
  backend evidence passed 16 tests with three environment skips; frontend
  evidence passed three tests, with Ruff, scoped lint, typecheck, formatting
  and build green. The single Package 5 aggregate gate passed 85 backend/
  PostgreSQL migration and concurrency tests plus 58 Package 5/R14-B frontend
  tests; contracts regenerated byte-stably and the final build passed. No live
  basemap licence, methodology approval or external validation is claimed.
- **Package 5 closure review and corrections (27 Aug 2026):** one independent
  clean-context review found four P1 projection/authority gaps: advertiser
  reads could select a different membership after disclosure authorization;
  source/link retries were not re-bound to the current tenant; stale
  recommendations retained cells/provenance; and advertiser reports exposed
  route-level trip identifiers inside the detailed score projection. The
  bounded correction now uses one active-organization authority with a stable
  tie-break, rejects moved-tenant or inactive retries, returns empty stale
  projections in API and UI, and publishes an aggregate-only advertiser score
  contract. All four red/green groups passed 11 focused tests; isolated
  PostgreSQL tenant/concurrency checks passed three tests, relevant contract
  checks passed four, preserved R14-B fixtures passed 89, and frontend lint,
  typecheck, formatting and build passed. Two stale verification assertions
  were corrected test-only and passed. The review follow-up transport returned
  no message twice, so no duplicate reviewer was started; controller diff,
  remote and focused-evidence checks confirm the original four findings are
  resolved.
- **Closure:** PKG-05 is DONE. All owned checklist rows 44–54 have verified
  implementation, one single Package 5 aggregate gate and one consolidated
  review/correction cycle. `EXT-LEGAL-PRIVACY`, `EXT-REPORT-METHOD`,
  `EXT-AD-PLATFORM` and `EXT-BASEMAP` remain honest live-use/reporting gates and
  do not block the next provider-neutral package.
- **Package 5 frontier closure (25 Aug 2026; superseded by build-first
  work):** the consolidated privacy,
  authorization and minimal-change review returned PASS after real-PostgreSQL
  evidence, control-state timing and unrelated formatting were reconciled.
  W3-00A/D/C and W3-01A/B were complete at that checkpoint. Its then-recorded
  storage/KYC/evidence blockers were later corrected by provider-neutral
  completion of the required Package 4 foundations: W3-00B and W3-00E are now
  DONE. W3-01C/D and W3-02A/B are now also implemented and verified; Package 5
  remains in REVIEW until its consolidated closure review passes.
- **W3-00B checkpoint evidence (26 Aug 2026):** migration `0062` records one
  lifecycle-guarded access/rectification/erasure case and append-only evidence
  for database, private objects, device queue, operational logs, backups and
  processors. Active-admin and identity checks, all-six-location completion,
  exact-retry convergence, changed-retry conflict and blank-by-default approved
  exception references fail closed. The database inventory covers account,
  KYC/vehicle, raw/derived/replay/impression, fraud, payout/financial,
  notification and audit classes; managed objects are verified through the
  provider-neutral storage port, with missing/mismatched/unavailable storage
  refused. Database/object erasure cannot be claimed while records remain, so
  immutable money/audit facts are preserved. Backup tooling now enforces both
  newest-14 and hard 1–35-day age bounds. Focused API/privacy/config/contract,
  PostgreSQL race/migration/autogenerate and backup checks pass, including
  observed red/green storage-outage evidence and a real local six-location
  access dry run (118 records across 19 database classes, zero object records,
  six evidence rows, completed). All three §9 baselines moved together. `EXT-LEGAL-PRIVACY`, named
  processors/regions, response rules and production exception decisions remain
  MISSING; no real DSR, deletion or legal validation is claimed.
- **W3-00E checkpoint evidence (26 Aug 2026):** migration `0063` adds
  append-only measurement runs and proof bindings with frozen period/source,
  formula/method, creative, approved installation-evidence, activation and
  correction-lineage fingerprints. Admin issuance is actor/request idempotent;
  changed sources create a linked reissue, while missing proof or incomplete
  ROI prerequisites fail closed. Campaign Performance Analysis reads the
  current reproducible frozen run; local/test ROI is possible only when every
  input is explicitly synthetic, and production issuance/method references
  remain blank/default-denied. Focused evidence: 24 measurement/methodology/
  disclosure passes with seven environment skips, four real-PostgreSQL
  concurrency/migration/immutability/autogenerate passes, two OpenAPI drift
  passes and Ruff clean. No live report, client method approval,
  conversion/revenue input or ROI claim is asserted; `EXT-REPORT-METHOD` and
  privacy live-use gates remain MISSING.
- **Extended Pro correction pass (25 Aug 2026):** four validated defects were
  repaired on the published Package 5 head without reopening Packages 1–4:
  migration `0047`'s PostgreSQL partial active-link index is now declared in
  ORM metadata with a SQLite partial predicate and an autogenerate regression;
  heatmap contributor suppression now covers every serialized metric rather
  than only the selected weight; source monitoring and admin heatmap services
  now require an active admin before domain reads; and governed advertiser
  output deterministically selects the newest active organization membership
  after the live gate. Focused red/green regressions pass, followed by the
  impacted Package 5 backend/migration subset (42 passed, 2 warnings). The
  post-repair aggregate backend gate is 968 passed, 3 skipped; frontend lint,
  typecheck, 212 unit tests, contract drift and the webpack build pass, and
  pre-production verification is 26 passed. The local Playwright attempt
  reached 63 passed and 6 skipped but had 9 environment-only failures because
  the running API is mounted from another worktree with stale seeded state and
  the cleanup path lacked `PAYOUT_CRYPTO_KEYRING_B64`; it is not attributed to
  these repairs and was not rerun. No external gate changed, and Package 6's
  separate W3-03A checkpoint was not touched.
- **Audit-correction adoption (25 Aug 2026):** Package 6 selectively adopted
  the net Package 5 product, test and contract corrections without the source
  branch's delivery receipts. Its colliding draft migration was reconciled as
  linear migration `0051` after Package 6's published `0050`; `0048`–`0050`
  remain unchanged. One canonical impression authority now governs workers,
  reports, payouts and heatmaps while scenarios remain inspectable; stale
  provenance, full-slice heatmap conservation and service-layer active-admin
  checks fail closed. Frontend notification state/retry and Cardvert branding
  corrections moved with synchronized contracts. Focused verification and the
  combined gate passed (1,058 backend passes, 4 skips; 225 frontend tests plus
  typecheck/lint/build; isolated migration/seed/live-stack checks). The sole
  bounded review's worker-authority finding was corrected with observed
  red/green evidence. Package 5 and Package 6 remain honestly BLOCKED at their
  existing external/dependency frontiers; no later slice was admitted.
- **Closure:** privacy/measurement review proves suppression, reproducibility,
  provenance and safe claims before any advertiser live-use gate opens.

### PKG-06 — matching and driver onboarding

- **Owns:** checklist 55–60. Matching/offers/activity and public application,
  KYC/payee and vehicle approval become one governed eligibility journey.
- **W3-04B evidence (27 Aug 2026):** migrations `0068`–`0069` add immutable
  person/payee submissions, decisions, digest-only applicant mutation access
  and exact-version payout verification while reusing the existing encrypted
  KYC, managed-file and canonical payee/account authorities. Approval requires
  actual audited reads of the current NIN, account and submission-bound clean
  documents; stale/replaced, rejected, expired, unsafe, unreadable or
  key-unavailable evidence fails closed. Applicant account capture is never
  payout authority: only authorized admin/provider verification promotes the
  exact version, and routine ciphertext rewrap preserves that authority without
  authorizing an unverified source. Historical retries converge across
  resubmission, conflicting retries fail, public status remains non-enumerating,
  and approval remains non-work-eligible until W3-04C. Observed red/green
  regressions, 54 focused backend checks, 4 real-PostgreSQL migration/concurrency
  checks, 103 frontend/R14-B checks, type/lint/build, byte-stable §9 contracts
  and a bounded browser pass succeeded. Independent threat/privacy/money review
  found four authority defects plus one rewrap seam; all five were corrected
  with focused regressions and the original findings closed. Live legal/privacy,
  KYC/bank provider, email, storage/scanner and key-custody facts remain external
  go-live gates and are not claimed.
- **W3-04C evidence (27 Aug 2026):** migration `0070` adds one owner-scoped,
  versioned vehicle profile and immutable pending/approved/rejected/expired
  evidence and decisions while reusing the managed-file, person/payee,
  assignment and trip authorities. Material revisions and expiry close work
  eligibility without rewriting history; only a current approved active owned
  vehicle can receive or activate an assignment or start a trip. Sensitive
  reads require an authoritative storage object and produce exact audited
  evidence; missing/unavailable objects fail closed. Identical concurrent
  decisions converge after serialization, and person/payee/NIN producers share
  eligibility-lock-before-profile ordering with assignment/trip consumers.
  Observed red/green regressions, 119 focused backend/PostgreSQL/security
  checks, 14 final vehicle/migration/contract checks, populated migration and
  append-only guards, 311 frontend tests, type/lint/build, byte-stable §9
  contracts and the rendered application vehicle flow passed. The independent
  security/concurrency review found three authority defects; all were corrected
  in `fe5d1ca` with focused regression evidence and the same reviewer returned
  PASS. Live legal/privacy, storage/scanner, key-custody and physical approval
  facts remain external go-live gates and are not claimed.
- **W3-03B/C audit-correction evidence (25 Aug 2026):** a newly materialized
  DB-time expiry is durably committed only through its typed transaction
  boundary, while generic errors roll back and list pages use statement-time
  database authority without duplicate service sweeps. Activity reads only the
  configured current analytics formula; a recovered weekly/inactivity flag can
  reopen on the same locked identity with one new event/notice and preserved
  history. Malformed or failed cursor load/persistence now fails the worker
  visibly while committed evaluations retry idempotently. Observed red/green,
  80 focused assignment/activity/worker/notification/exclusivity passes, 11
  real-PostgreSQL decision/reopen/lock/clock barriers, scoped static checks and
  one consolidated Sol High review PASS. No migration, public contract,
  Package 7 path or external-gate state changed.
- **W3-03A evidence (25 Aug 2026):** `matching_v1` adds an admin-only,
  non-persistent cars-only recommender over current assignment readiness. It
  ranks lower vehicle/driver load, then computed-only activity and stable UUID
  ties; the admin must explicitly select a candidate. A typed fingerprint is
  rechecked under stable parent and aggregate-contributor row locks before the
  existing assignment command writes, while context-free manual clients remain
  compatible. Evidence includes observed red/green, 35 focused backend passes
  plus 10 real-PostgreSQL concurrency/exclusivity passes, 56 frontend/R14-B
  passes, type/lint/build, byte-stable regenerated §9 artifacts, an isolated
  admin recommendation→offer journey, and consolidated review RESOLVED. No
  migration, automatic assignment, person/payee/KYC eligibility claim, provider
  input or live-use authorization was added. W3-03B–W3-04C were not started;
  the corrected Package 5 history is adopted beneath this checkpoint and its
  external legal/reporting/ad-platform gates remain unchanged.
- **W3-03B evidence (25 Aug 2026):** migration `0048` adds canonical,
  explicitly expiring assignment offers whose complete payout-v3, campaign
  window, service-area, zone and selected-creative evidence is fingerprinted
  and shown to the driver. Accept/decline/expiry decisions use database time,
  one campaign→assignment→eligibility lock order and append-only evidence;
  acceptance binds only the frozen offer snapshot. An idempotent worker and
  lazy reads materialize expiry. Final activation is admin-only and composes
  every built review/funding/hold gate, then fails closed because Package 4's
  approved-creative and installation-evidence authorities are not yet built.
  Create/cancel services require an active admin, while terminal assignment
  transitions and trip start serialize without resurrecting work or forking
  event history. Evidence includes 86 focused real-PostgreSQL passes plus the
  funded deactivation/trip barrier, 69 fast backend/API passes, populated
  migration and append-only demo-seed roundtrips, 213 frontend tests plus 11
  focused lifecycle UI tests, type/lint/format, byte-stable §9 artifacts, and
  one consolidated Luna review PASS after seed/UI corrections. W3-03C–W3-04C
  remain unstarted; external Package 4/5 gates remain unchanged.
- **W3-03C evidence (25 Aug 2026):** migration `0049` adds dedicated
  assignment-activity operations flags plus append-only opened/recovered
  evidence. The fixed seven-day rule uses the later of activation or latest
  verified activity at an exact database-clock boundary; the weekly rule uses
  the immediately completed Monday-to-Monday UTC window and only runs when
  operations explicitly configures a positive verified-hours floor. Missing,
  invalid, insufficient, blocked, future, stale or wrongly linked analytics
  never become verified activity, while missing weekly configuration does not
  disable inactivity protection. The worker uses the established rolling
  cursor, configured batch bound and one transaction per assignment; retries,
  concurrent opens/recoveries and failures converge without starving the tail.
  Admins see a sanitized review projection and drivers receive deduplicated
  in-app open/recovery notices; no assignment, trip, earnings, hold, payee or
  payout state is changed. Evidence includes 65 focused backend/API/worker/
  migration passes, 3 isolated real-PostgreSQL concurrency and populated-
  migration passes, 5 focused admin/notification UI passes, 73 preserved
  driver/PWA contract fixtures, type/lint/format, byte-stable §9 regeneration
  and consolidated Luna review PASS after the bounded-worker/head-guard
  correction. No weekly policy value, external input, live-use approval,
  automatic termination or Package 7 work was added.
- **W3-04A evidence (25 Aug 2026):** migration `0050` adds a dedicated,
  pending-only public driver application linked one-to-one with an invited
  driver user and pending profile. The default-off cohort flag and separate
  atomic Redis IP/email/global limiter fail closed; new, duplicate and
  same-email-race requests return one non-enumerating pending envelope with a
  fresh high-entropy reference, while only a real new application persists its
  digest and one creation audit. The random unreachable credential grants no
  session or work authority. Known and unknown references expose the same
  limited status; the active-admin service gate protects a sanitized queue.
  Both Compose contracts and environment examples carry the feature/limiter
  controls. All three §9 baselines moved together. Evidence includes observed
  red/green, 117 focused backend/PostgreSQL/real-Redis/migration/autogenerate/
  contract/pre-production passes, 54 focused frontend and preserved R14-B
  passes, a live isolated apply→reference→pending-status journey, and a
  consolidated Luna review PASS after fail-closed, audit-amplification and
  deployment corrections. The single Package 6 backend aggregate recorded
  1,037 passes and 12 stale historical/Package-6 harness expectations; the 12
  were corrected and all affected checks passed without repeating the full
  suite. The frontend aggregate passed 224 tests, typecheck, lint and build.
  No KYC, payee, vehicle, document, tracking, earnings, live applicant or
  Package 7 authority was added. W3-04B/C remain dependency-blocked.
- **Closure:** security/privacy/money and lifecycle races pass, including the
  complete accept/decline/expiry flow and non-work-eligible pending states.

### PKG-07 — production driver PWA

- **Owns:** checklist 61–64. Installability/session safety, screen-on tracking,
  durable sync, onboarding/campaign use, earnings/disputes and release evidence
  ship together.
- **Package plan (activated 25 Aug 2026, canonical programme line
  `feat/pkg-04-build-first`):**
  W4-01A hardens the installable shell, same-origin BFF session and live-held
  ADR 014 runtime/storage/writer gates before W4-01B composes the complete
  screen-on Start/capture/flush/End flow. A focused PWA/security/data-loss gate
  follows W4-01B. W4-01C is now executable after W3-04C and W2-03D closed; it
  owns client integration only and cannot invent live KYC/vehicle evidence.
- **Entry correction:** PKG02-C2 is mandatory before W4-01A becomes
  authoritative or any real GPS is collected: the tracker enforces ADR 014
  capability/session gates, stale writer-lock state is recoverable, and
  terminal ping failures remain as dead-letter evidence.
- **W4-01A evidence (DONE 25 Aug 2026):** commit `a1afde1` keeps the existing
  D15/D16 protocol and BFF-cookie boundary while making Start acquire the
  exclusive writer before the server call, retaining the lock through unknown
  Start reconciliation, and deriving `active | degraded | stopped` only from
  currently held visibility, wake, location, session, storage and writer
  guarantees. The Cardvert manifest/service worker is installable and
  auth-safe; keepalive, renewal, revocation and logout are server-validated.
  Location-bearing IndexedDB records and terminal dead letters are encrypted,
  driver-bound and migrated in place from the shipped v1 database; terminal
  failures remain local diagnostic evidence and force an incomplete client
  watermark. Six unchanged-code break cases failed before the implementation.
  Focused frontend evidence passed (112 worker tests; controller high-risk
  recheck 51 tests), with typecheck, scoped lint/format, production build, eight
  desktop/mobile browser checks, an authenticated live fail-closed Start check,
  and byte-stable §9 artifacts. Independent review found two data-loss defects
  (the historical database-name discontinuity and concurrent queue mutation);
  both gained deterministic red/green regressions and the recheck passed. No
  physical-device, native/background, real-GPS, route/battery, staging, pilot,
  KYC/vehicle or Package 8 evidence is claimed.
- **W4-01B evidence (DONE 25 Aug 2026):** commit `cc2f0d8` completes the
  screen-on D15/D16 flow without changing the backend contract. End joins any
  active drain, cuts and drains stable batches before reading durable counters,
  refuses a watermark after storage/identity/writer/runtime loss, and reconciles
  cancelled or ambiguous End authority under the held writer before resuming or
  releasing. Only complete accepted/duplicate/quarantined acknowledgements
  delete a batch; malformed/lost responses retain the identical key and
  payload, while terminal rejection remains encrypted dead-letter evidence.
  Seven observed red cases preceded the change. The single frontend aggregate
  passed 277 tests, typecheck, scoped lint/format, production build and 14
  authenticated desktop/mobile Playwright checks; controller P7-K1 checks
  passed 107 combined high-risk tests and frozen §9 artifacts remained
  byte-stable. The independent P7-K1 review found an overbroad migration-owner
  failure classifier and stale §8 wording. Tri-state ownership now fails queue
  opening on every unavailable/non-authoritative result, recognizes only exact
  `404/TRIP_NOT_FOUND` as non-ownership, and recovers rightful-owner evidence
  without sequence/watermark collision; deterministic red/green regressions and
  two bounded rechecks passed. Architecture §8 now matches the built Cardvert
  session, encrypted queue, cache and writer/End behavior.
- **W4-01C evidence (DONE 27 Aug 2026):** commit `56d855d` composes the
  canonical application, person/payee, vehicle, offer, activation and current-
  trip authorities into one server-projected PWA journey without adding a
  client readiness truth or changing backend contracts. Pending, rejected,
  expired, conflict, unavailable and degraded states fail closed; privileged
  operations retain the same-origin BFF/session boundary, and explicit Start/
  End retains W4-01A/B encryption, single-writer, retry and foreground-only
  tracking. Two observed red cases exposed the former hard-coded readiness and
  missing onboarding bridge. The corrected checkpoint passed 339 frontend
  tests across 67 files, typecheck, full lint, scoped format, production build,
  synthetic Pixel 7 READY→Start→active→End and iPhone-sized degraded-evidence
  no-Start/public-bridge journeys, plus a clean-context post-build review PASS.
  No backend, API, schema, migration or §9 baseline changed. Physical devices
  and live storage/scanner/KMS/provider/legal authorization remain external
  gates and are not claimed.
- **W4-01D evidence (DONE 28 Aug 2026):** commit `4fc102d` completes canonical
  campaign/trip history, `payout_v3` earnings, public hold/dispute/outcome and
  sanitized notification journeys without adding a client money, fraud or
  readiness authority. Successful-empty and unavailable reads are distinct;
  stale money/hold state is hidden across offline, revocation and cache
  transitions, privileged offline mutation is blocked, and the service worker
  caches static assets only. Four observed-red regressions preceded the change.
  The corrected checkpoint passed 30 focused frontend tests, 48 backend
  authority tests with 30 environment-gated skips, the single Package 7
  aggregate of 352 frontend tests across 69 files, typecheck, full lint,
  scoped formatting and production build. The preserved W4-01C journey and the
  W4-01D Chromium/mobile-WebKit production rehearsal passed. One consolidated
  clean-context Package 7 review returned PASS after offline freshness,
  reconnect and notification-cache corrections. Backend, migrations and all
  architecture §9 contract baselines stayed unchanged. Evidence is recorded in
  `docs/pkg-07-w4-01d-release-rehearsal.md`.
- **Closure:** PKG-07 is DONE. W4-01A/B/C/D are integrated and reviewed against
  the frozen backend contracts. Physical Android/iPhone install/update,
  representative route/battery/SLO evidence, actual WebKit offline toggling,
  native signing/store/push, live providers, staging and pilot execution remain
  honest external/live gates and are not claimed.

### PKG-08 — governed reporting and pilot readiness

- **Owns:** checklist 65–68. Governed map/report output, bounded exports,
  client-owned environment and the full acceptance suite form the launch gate.
- **Package plan (activated 28 Aug 2026, canonical programme line
  `feat/pkg-04-build-first`):** W4-02A first composes existing governed
  measurement runs, disclosure controls, safe map labels and conditional ROI
  into the admin/advertiser report experience. W4-02B then issues bounded,
  reproducible CSV/PDF artifacts from that frozen authority. W4-03A remains a
  client-owned live environment gate after its provider-neutral preparation is
  exhausted; W4-03B assembles the synthetic acceptance machinery while leaving
  real permits, providers, approved methodology and pilot facts fail-closed.
  The production basemap account/licence is a live-release gate and does not
  block provider-neutral/local W4-02A implementation. Each checkpoint receives
  focused verification; Package 8 receives one aggregate gate and one
  consolidated review at honest closure.
- **W4-02A evidence (DONE 28 Aug 2026):** commit `c7d5945` composes advertiser
  Campaign Performance Analysis and governed map output from one immutable
  measurement run/result/score/zone provenance chain. Performance-only runs
  contain no ROI text; a financial result appears only when the frozen run and
  result carry the complete approved method/input decision. Advertiser geometry
  is limited to disclosure-cleared ranked targets, while suppressed, stale,
  empty, unavailable, inconsistent, role and tenant failures expose no map or
  report value. The local MapLibre default is provider-neutral and bounded by a
  fail-closed readiness timeout; no production basemap claim is made. Admin
  monitoring retains purpose-scoped raw-route authority and gains complete
  run/formula/source provenance. The checkpoint passed 21 focused frontend
  tests, typecheck, scoped lint/format and production build; 54 focused PostGIS
  tests and Ruff; a synthetic browser journey spanning performance-only,
  qualified synthetic ROI, unavailable map, cross-tenant 404 and role denial;
  and one clean-context privacy/measurement/maps review PASS after lineage,
  ranking and provenance corrections. No API schema, generated contract,
  database model or migration changed. Evidence is recorded in
  `docs/pkg-08-w4-02a-governed-maps-report.md`; `EXT-BASEMAP`,
  `EXT-REPORT-METHOD` and `EXT-LEGAL-PRIVACY` remain live gates.
- **W4-02B evidence (DONE 28 Aug 2026):** commit `26f5e22` adds migration
  `0071` and one immutable, versioned report-issuance/artifact authority for
  deterministic CSV/PDF generation from a frozen W4-02A measurement decision.
  Request replay, concurrent version allocation, worker lease/recovery,
  partial-object failure, append-only reissue, current authorization and
  privacy/method rechecks, hash/tamper detection, renderer bounds and private
  stored-file download all fail closed. Performance-only artifacts contain no
  ROI wording; conditional financial output requires the qualified frozen
  `INCLUDE` decision, and person/segment export remains disabled. The corrected
  checkpoint passed 86 focused backend/PostgreSQL tests with one skip, a real
  MinIO conditional-write race, 14 report UI/BFF tests, 99 preserved R14-B
  fixtures, typecheck, scoped lint/format, production build, byte-stable
  regeneration of all three synchronized §9 baselines, and structural plus
  rendered visual PDF inspection. One clean-context privacy/measurement/
  security review returned PASS after exact-retry, status-time authority,
  stored-file immutability and provider-boundary corrections. Evidence is in
  `docs/pkg-08-w4-02b-bounded-issuance.md`. `EXT-REPORT-METHOD` and
  `EXT-LEGAL-PRIVACY` continue to gate live issuance.
- **W4-03A provider-neutral preparation evidence (28 Aug 2026):** commits
  `4db90d4` through `2d83d3d` add fail-closed production configuration and edge
  contracts, pinned release dependencies and images, structured redacted
  observability, health/readiness, deterministic release/failure-stop,
  encrypted database/private-object backup, isolated restore and previous-image
  recovery procedures. The exact-tip focused suite passed 65 tests; the
  pre-production gate passed 91 tests; the unsafe-input slice passed 38 tests;
  the production-like rehearsal passed migration, repeated restore,
  object-version cleanup, recovery, bounded load and deliberate traffic
  fail-stop. A narrow final `$minimal-change-review` returned PASS after
  storage-host, proxy-trust, backup-output and multicast corrections. Evidence
  is in `docs/pkg-08-w4-03a-preparation.md` and
  `docs/w4-03a-release-operations.md`. Checklist W4-03A remains TODO for the
  approved client-owned environment, `EXT-STAGING-APPROVAL` and
  `DV-STAGING-LIVE`; no live deployment is claimed.
- **W4-03B-P1 gate-evaluator evidence (28 Aug 2026):** commit `79f7837`
  adds one read-only command that evaluates the six §35.3 gates from committed
  progress/architecture/decision authority plus a bounded runtime-claim
  allowlist. Current authority produces six ordered `BLOCKED` lines and exit
  `1`; a fully complete synthetic fixture produces six `PASS` lines and exit
  `0`; malformed or contradictory claims fail closed with exit `2` and a
  sanitized diagnostic. The focused suite passed 17 tests plus lint,
  compilation and delivery-control validation. A clean-context
  `$minimal-change-review` found no scope defect and requested four additional
  regression cases, which pass at the integrated tip. No authority document,
  runtime business logic, provider state or external/live evidence changed.
- **W4-03B-P2 synthetic-journey evidence (28 Aug 2026):** commits `c68d9a1`
  and `cb77eef` add one correlated Abuja acceptance command spanning synthetic
  advertiser/admin setup, screen-on PWA and GPS simulation, measurement,
  Campaign Performance Analysis, qualified synthetic conditional ROI,
  aggregate contextual activation, a frozen payout instruction and
  incident/recovery conservation. The command passed its backend and
  mobile-Chrome path and accepted only the evaluator's six exact ordered
  `BLOCKED` lines; forged approval, cross-tenant access, provider calls, live
  GPS, report issuance and changed recovery receipts fail closed. Ten focused
  pytest checks, the preserved W4-01C proof and scoped Python/frontend static
  checks passed. One clean-context `$minimal-change-review` requested a single
  bounded correction restoring shared fixture defaults, making advertiser-first
  setup W4-03B-specific and adding missing red evidence. W4-03B remains TODO;
  no external/live gate or provider state changed.
- **W4-03B-P3 target-area coverage evidence (28 Aug 2026):** commits `b65a815`
  and `f99fd73` implement the adopted synthetic/test-only formula as the
  geography area of the union of clipped, disclosure-cleared qualifying fixed
  cells divided by the frozen target-zone area. Immutable provenance binds
  tenant, campaign, complete half-open period, zone/grid revisions, cell
  identity/geometry, disclosure and qualifying references, and a canonical
  hash. The Abuja golden fixture deterministically produces `62.500000%`; 22
  focused PostGIS tests cover union/overlap, clipping, scope, disclosure,
  omission, geometry, replay and the below-target case, while seven existing
  methodology/disclosure tests and scoped static checks pass. One transient
  database-connection timeout passed on its single focused retry. The sole
  clean-context `$minimal-change-review` requested one bounded grid-authority
  and duplicate-evidence correction. No public contract or §9 baseline moved;
  `EXT-REPORT-METHOD` and all privacy/live gates remain MISSING.
- **W4-03B-P4 local load/reproducibility evidence (28 Aug 2026):** commit
  `63beccf` adds one provider-neutral command for the confirmed synthetic Abuja
  cohort (10 vehicles, five advertisers, nominal 92 days compressed to ten
  samples per operation). It records nearest-rank p50/p95 for Campaign
  Performance Analysis, governed heatmap provenance and report-worker artifact
  pairs against explicitly synthetic-only 2,000 ms regression ceilings, plus
  deterministic input/result/CSV/PDF hashes. The stable run passed with all 35
  focused tests and scoped Ruff checks; timeout, threshold, operation, network,
  drift, coverage and renderer failures are fail-closed and sanitized. One
  clean-context `$minimal-change-review` requested a bounded command-level
  sanitized-error correction. The harness preserves the six exact live-gate
  blockers and claims no production SLO, burn-in, provider or external action.
- **Package 8 consolidated review/correction (28 Aug 2026):** the independent
  review of `1e194cf..295cb7d` passed the aggregate synthetic journey, local
  load/reproducibility commands, delivery control and synchronized §9
  baselines, and found no unrelated scope. Its sole P1 was production edge and
  storage acceptance of special-use host authorities. Commit `cc4cd13` rejects
  every edge IP literal and reserved DNS family, applies the DNS rule to
  storage while preserving intentional RFC1918 private storage, reconciles the
  W4-03A evidence record, and passed 42 focused boundary tests, an 80-test
  release-environment selection, scoped Ruff/diff checks and one clean-context
  `$minimal-change-review` PASS. W4-03A/B are now provider-neutral/synthetic
  complete and external/live-only; neither checklist is marked DONE.
- **Closure:** every §35 gate is evidenced; restore, security, load, report
  reproducibility and end-to-end pilot simulation pass.

### PKG-09 — controlled pilot, training and handover

- **Owns:** checklist 69–71. Training is rehearsed before a controlled pilot;
  stabilization evidence then closes support, ownership and roadmap handover.
- **Package plan (activated 28 Aug 2026):** W4-04A-P1 first authors role-task
  inventories and operator procedures from built admin/advertiser/driver
  surfaces. W4-03C-P1 then prepares pilot telemetry, rollback, payout/report
  replay, incident and evidence-capture templates and exercises them only with
  synthetic data. W4-04B-P1 finally assembles the documentation index, RACI
  role skeleton, support/SLA/escalation templates, external/deferred risk
  register and evidence-linked roadmap. These internal preparation checkpoints
  do not satisfy their parent checklist rows: facilitated rehearsal, approved
  users, live pilot telemetry, named owners, credential handover and sign-off
  remain external/live gates. Each checkpoint receives focused verification;
  Package 9 receives one consolidated review after preparation stabilizes.
- **W4-04A-P1 role-training preparation (28 Aug 2026):** commit `c182181`
  adds actual-route admin/advertiser/driver task inventories, six-domain
  operator procedures and a deterministic local-link, command, role, coverage
  and false-live-claim audit. Six focused tests, the documented audit command,
  Python compilation and diff checks pass. The single clean-context
  `$minimal-change-review` found unresolved `python` command references; the
  bounded correction standardizes `python3`, validates interpreter availability
  and reruns the affected evidence. Facilitated rehearsal, user acceptance and
  live operation remain unclaimed; `EXT-RELEASE-ENV`,
  `EXT-STAGING-APPROVAL` and `EXT-OPERATIONS-OWNER` remain missing.
- **W4-03C-P1 pilot-operations preparation (28 Aug 2026):** commit `1ae55da`
  adds a six-domain operations pack for telemetry/readiness, rollback,
  payout/report replay, incident response and evidence capture, plus a
  deterministic synthetic exercise matrix and focused guard. The validator
  CLI, seven validator tests, thirteen synthetic exercises, Python compilation,
  scoped Ruff and diff checks pass; the clean-context
  `$minimal-change-review` returned PASS with no findings or evidence gaps.
  No deployment, payment, provider, physical-device, user or pilot action was
  performed. `EXT-RM2-POLICY` and `EXT-PILOT-FACTS` remain PRESENT; every other
  W4-03C external/live prerequisite remains MISSING.
- **W4-04B-P1 handover preparation (28 Aug 2026):** commit `ddbd576` adds
  an evidence-linked documentation index, placeholder-only role/RACI and
  support/SLA/escalation templates, exact external/deferred risk register,
  credential-custody checklist and evidence-linked post-MVP roadmap. The
  focused audit reports six files, 29 external gates and three deferred
  validations; thirteen focused tests, Python compilation, scoped Ruff and
  diff checks pass. Its single clean-context `$minimal-change-review` returned
  FIX for three bounded audit/coverage findings; those were remediated and the
  affected evidence rerun under the no-loop rule. No credential, account,
  owner, acceptance, handover, deployment or live-pilot claim was created.
- **Package 9 consolidated review/correction (28 Aug 2026):** the independent
  review of `e307b30..803155e` returned FIX only for a missing placeholder-only
  backup schedule, cross-pack role vocabulary drift and training/pilot guards
  that duplicated gate truth. Commit `9095725` adds the indexed backup schedule,
  canonicalizes roles without collapsing incident/security or payout
  maker/checker/reconciler duties, and derives training/pilot gate checks from
  `docs/progress.md`. The correction received `$minimal-change-review` PASS;
  all three validator CLIs and 31 focused tests pass after integration. The
  remaining queue is external/live-only and no EXT/DV state changed.
- **Closure:** accepted operating materials, monitored pilot evidence, known
  risks/deferments and named owners agree with repository truth.

### PKG-10 — admitted Cardvert audit remediation

- **Owns:** remediation slices R01–R60.
- **Outcome:** all 86 Pro-admitted FIX candidates are implemented and verified
  exactly once through the immutable slice/candidate/dependency register below.
  The 9 DEFER, 12 OWNER DECISION and 8 EXTERNAL INPUT candidates remain
  non-executable and retain their admitted evidence/activation conditions.
- **Execution:** the scheduler continuously selects the highest-priority ready
  non-conflicting work and refills up to two implementation leases immediately.
  Central configuration, migrations, contracts, generated baselines, shared
  fixtures, and this control file remain serialized. Detailed leases, waits,
  model gates, receipts and next actions live in
  `.codex/delivery/cardvert-audit-remediation/plan-ledger.md`; this file records
  only accepted register state.
- **Admission:** a slice may move from `QUEUED` to `ACTIVE` only when its named
  plan review is `PASS` and every registered dependency is `COMPLETE`. It moves
  to `COMPLETE` only after its own diff review and exact named domain checkpoint
  also pass. Slice numbering is stable identity, not topological order; the
  admitted R09 → R10 dependency is intentional.
- **Closure:** PKG-10 is `DONE` only when all 60 rows are `COMPLETE`, integrated
  domain gates pass, R59 supplies the mutating real-stack release journey, R60
  reconciles final current-state architecture/routes/migrations, and a final
  proportional minimal-change review accepts the integrated programme.

## Remediation slice register

The candidate IDs, direct dependency sets and checkpoint codes are immutable
admission data. Review receipts use the slice-bound forms `RNN-P`, `RNN-M` and
`RNN-CP-CODE`; a receipt in this register is an acceptance pointer, not proof by
assertion. The controller must inspect and record its supporting evidence in the
durable ledger before changing a row.

| Slice | Candidate IDs | Dependencies | State | Plan review | Diff review | Domain checkpoint |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | GOV-001 | none | COMPLETE | PASS — R01-P | PASS — R01-M | CP-CONTROL PASS — R01-CP-CONTROL |
| R02 | GOV-003, TST-001, DB-005 | R01, R04 | COMPLETE | PASS — R02-P | PASS — R02-M | CP-CONTROL PASS — R02-CP-CONTROL |
| R03 | GOV-004 | R02 | COMPLETE | PASS — R03-P | PASS — R03-M | CP-CONTROL PASS — R03-CP-CONTROL |
| R04 | DB-004 | none | COMPLETE | PASS — R04-P | PASS — R04-M | CP-DB PASS — R04-CP-DB |
| R05 | DB-001, TST-012, ONB-010 | R02, R04 | COMPLETE | PASS — R05-P | PASS — R05-M | CP-DB PASS — R05-CP-DB |
| R06 | DB-002 | R02, R04, R05 | COMPLETE | PASS — R06-P | PASS — R06-M | CP-DB PASS — R06-CP-DB |
| R07 | DB-003 | R02, R04, R06 | COMPLETE | PASS — R07-P | PASS — R07-M | CP-DB PASS — R07-CP-DB |
| R08 | GOV-005 | none | COMPLETE | PASS — R08-P | PASS — R08-M | CP-SECURITY PASS — R08-CP-SECURITY |
| R09 | GOV-007, AUT-001, AUT-002 | R10 | COMPLETE | PASS — R09-P | PASS — R09-M | CP-SECURITY PASS — R09-CP-SECURITY |
| R10 | AUT-005 | R08 | COMPLETE | PASS — R10-P | PASS — R10-M | CP-SECURITY PASS — R10-CP-SECURITY |
| R11 | AUT-004 | R09 | COMPLETE | PASS — R11-P | PASS — R11-M | CP-SECURITY PASS — R11-CP-SECURITY |
| R12 | AUT-003, REL-003 | R11 | COMPLETE | PASS — R12-P | PASS — R12-M | CP-SECURITY PASS — R12-CP-SECURITY |
| R13 | SEC-001, PRV-008 | none | COMPLETE | PASS — R13-P | PASS — R13-M | CP-PRIVACY PASS — R13-CP-PRIVACY |
| R14 | SEC-002, TST-004 | R12 | COMPLETE | PASS — R14-P | PASS — R14-M | CP-SECURITY PASS — R14-CP-SECURITY |
| R15 | GOV-006 | none | COMPLETE | PASS — R15-P | PASS — R15-M | CP-WORKERS PASS — R15-CP-WORKERS |
| R16 | GOV-008 | none | COMPLETE | PASS — R16-P | PASS — R16-M | CP-CONTROL PASS — R16-CP-CONTROL |
| R17 | TST-007 | R02, R03 | COMPLETE | PASS — R17-P | PASS — R17-M | CP-CONTROL PASS — R17-CP-CONTROL |
| R18 | MON-005, MON-006 | R04, R06, R07 | COMPLETE | PASS — R18-P | PASS — R18-M | CP-MONEY PASS — R18-CP-MONEY |
| R19 | MON-002 | R18 | COMPLETE | PASS — R19-P | PASS — R19-M | CP-MONEY PASS — R19-CP-MONEY |
| R20 | MON-001, DB-007, MON-008 | R05, R18 | COMPLETE | PASS — R20-P | PASS — R20-M | CP-MONEY PASS — R20-CP-MONEY |
| R21 | MON-003 | R20 | COMPLETE | PASS — R21-P | PASS — R21-M | CP-MONEY PASS — R21-CP-MONEY |
| R22 | MON-004, MON-007, MON-009 | R20, R21 | COMPLETE | PASS — R22-P | PASS — R22-M | CP-MONEY PASS — R22-CP-MONEY |
| R23 | COM-001, COM-004 | R08 | COMPLETE | PASS — R23-P | PASS — R23-M | CP-COMMERCIAL PASS — R23-CP-COMMERCIAL |
| R24 | COM-002 | R08, R23 | COMPLETE | PASS — R24-P | PASS — R24-M | CP-COMMERCIAL PASS — R24-CP-COMMERCIAL |
| R25 | COM-003, COM-005 | R08, R24 | COMPLETE | PASS — R25-P | PASS — R25-M | CP-COMMERCIAL PASS — R25-CP-COMMERCIAL |
| R26 | COM-006 | R08, R25 | COMPLETE | PASS — R26-P | PASS — R26-M | CP-COMMERCIAL PASS — R26-CP-COMMERCIAL |
| R27 | COM-007 | R08, R26 | COMPLETE | PASS — R27-P | PASS — R27-M | CP-COMMERCIAL PASS — R27-CP-COMMERCIAL |
| R28 | CAM-001 | none | COMPLETE | PASS — R28-P | PASS — R28-M | CP-CAMPAIGN PASS — R28-CP-CAMPAIGN |
| R29 | CAM-002 | R04, R08, R28 | COMPLETE | PASS — R29-P | PASS — R29-M | CP-CAMPAIGN PASS — R29-CP-CAMPAIGN |
| R30 | CAM-003 | R29 | COMPLETE | PASS — R30-P | PASS — R30-M | CP-CAMPAIGN PASS — R30-CP-CAMPAIGN |
| R31 | CAM-004 | R18, R19, R30 | COMPLETE | PASS — R31-P | PASS — R31-M | CP-CAMPAIGN PASS — R31-CP-CAMPAIGN |
| R32 | ONB-002 | none | COMPLETE | PASS — R32-P | PASS — R32-M | CP-ONBOARDING PASS — R32-CP-ONBOARDING |
| R33 | ONB-006 | R05, R32 | COMPLETE | PASS — R33-P | PASS — R33-M | CP-ONBOARDING PASS — R33-CP-ONBOARDING |
| R34 | OFF-001 | R04 | COMPLETE | PASS — R34-P | PASS — R34-M | CP-OFFLINE PASS — R34-CP-OFFLINE |
| R35 | OFF-002, OFF-003 | R34 | COMPLETE | PASS — R35-P | PASS — R35-M | CP-OFFLINE PASS — R35-CP-OFFLINE |
| R36 | OFF-005 | R35 | COMPLETE | PASS — R36-P | PASS — R36-M | CP-OFFLINE PASS — R36-CP-OFFLINE |
| R37 | OFF-006 | R36 | COMPLETE | PASS — R37-P | PASS — R37-M | CP-OFFLINE PASS — R37-CP-OFFLINE |
| R38 | PRV-001, PRV-002 | R13 | COMPLETE | PASS — R38-P | PASS — R38-M | CP-PRIVACY PASS — R38-CP-PRIVACY |
| R39 | PRV-003 | R38 | COMPLETE | PASS — R39-P | PASS — R39-M | CP-PRIVACY PASS — R39-CP-PRIVACY |
| R40 | PRV-004, AUD-001, AUD-002 | R16, R39 | COMPLETE | PASS — R40-P | PASS — R40-M | CP-PRIVACY PASS — R40-CP-PRIVACY |
| R41 | PRV-009, AUD-004, TST-010 | R40 | COMPLETE | PASS — R41-P | PASS — R41-M | CP-PRIVACY PASS — R41-CP-PRIVACY |
| R42 | PRV-005, PRV-006 | R41 | COMPLETE | PASS — R42-P | PASS — R42-M | CP-PRIVACY PASS — R42-CP-PRIVACY |
| R43 | PRV-007 | R42 | COMPLETE | PASS — R43-P | PASS — R43-M | CP-PRIVACY PASS — R43-CP-PRIVACY |
| R44 | AUD-005 | R16, R40 | COMPLETE | PASS — R44-P | PASS — R44-M | CP-PRIVACY PASS — R44-CP-PRIVACY |
| R45 | MET-003 | R04, R41 | COMPLETE | PASS — R45-P | PASS — R45-M | CP-REPORTING PASS — R45-CP-REPORTING |
| R46 | REP-001 | R45 | COMPLETE | PASS — R46-P | PASS — R46-M | CP-REPORTING PASS — R46-CP-REPORTING |
| R47 | MET-001, MET-002, MET-004, REP-002 | R41, R46 | COMPLETE | PASS — R47-P | PASS — R47-M | CP-REPORTING PASS — R47-CP-REPORTING |
| R48 | REP-003 | R47 | COMPLETE | PASS — R48-P | PASS — R48-M | CP-REPORTING PASS — R48-CP-REPORTING |
| R49 | REP-004 | R47, R48 | COMPLETE | PASS — R49-P | PASS — R49-M | CP-REPORTING PASS — R49-CP-REPORTING |
| R50 | REP-005 | R47, R49 | COMPLETE | PASS — R50-P | PASS — R50-M | CP-REPORTING PASS — R50-CP-REPORTING |
| R51 | REP-006 | R43, R49, R50 | COMPLETE | PASS — R51-P | PASS — R51-M | CP-REPORTING PASS — R51-CP-REPORTING |
| R52 | MET-006 | R51 | COMPLETE | PASS — R52-P | PASS — R52-M | CP-REPORTING PASS — R52-CP-REPORTING |
| R53 | REL-005 | none | COMPLETE | PASS — R53-P | PASS — R53-M | CP-RELEASE PASS — R53-CP-RELEASE |
| R54 | REL-006 | R12, R16, R53 | COMPLETE | PASS — R54-P | PASS — R54-M | CP-RELEASE PASS — R54-CP-RELEASE |
| R55 | REL-004 | R03, R18, R48, R51, R54 | COMPLETE | PASS — R55-P | PASS — R55-M | CP-RELEASE PASS — R55-CP-RELEASE |
| R56 | TST-005 | R09, R11, R14, R40 | COMPLETE | PASS — R56-P | PASS — R56-M | CP-SECURITY PASS — R56-CP-SECURITY |
| R57 | TST-008 | R19, R27, R49, R55 | COMPLETE | PASS — R57-P | PASS — R57-M | CP-RELEASE PASS — R57-CP-RELEASE |
| R58 | TST-011 | R15, R20, R21, R43, R49, R51 | COMPLETE | PASS — R58-P | PASS — R58-M | CP-WORKERS PASS — R58-CP-WORKERS |
| R59 | TST-002 | R22, R31, R33, R37, R41, R44, R48, R50, R51, R56, R57, R58 | COMPLETE | PASS — R59-P | PASS — R59-M | CP-RELEASE PASS — R59-CP-RELEASE |
| R60 | GOV-009 | R03, R17, R18, R22, R27, R31, R33, R37, R43, R44, R52, R55, R56, R59 | COMPLETE | PASS — R60-P | PASS — R60-M | CP-CONTROL PASS — R60-CP-CONTROL |

## Architecture traceability — non-executable parent groups

These 22 historical architecture groups are traceability only. They are not
packages, statuses, or review cycles and can never be promoted.

RM17's production-PWA/staging parallel intent is handled as disjoint internal work in
PKG-01 under its package plan; there are never two active packages.

| Order | Parent outcome | Type | Outcome and architectural authority | Prerequisites | Gate impact | Completion evidence required |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | **RISK-01 — production-PWA real-device proof** | PARENT | Android/iOS installable-PWA ADR and real-device proof for screen-on enforcement, permissions, visibility degradation, durable queue, tracking health, battery, reload/offline and session safety (§23, D18/RM17). Synthetic routes only. | Stable D15/D16 ping/seal contract **[BUILT]** | Produces early D18/RM17 evidence for **G-pilot**; authorises no real GPS | Browser/device matrix, measured SLO evidence, live synthetic-trip simulation, and independent review. |
| 2 | **RISK-02 — synthetic staging** | PARENT | Exercise the production-like topology with synthetic data before W2 grows it (§25, RM17). | Owner approval before external spend; Q32 blocks production, not preproduction work | Produces early RM17 evidence for **G-pilot**; authorises no live data | Deployment/recovery/smoke evidence or an explicit `BLOCKED` row naming the missing approval. |
| 3 | **W0-01 — stationary-time policy** | PARENT | Decide and implement RM2's sub-window rule (§16.1, §35 RM2; D2/D4/Q5). | Record the owner-approved money policy before code; obtaining it is part of this slice | Closes RM2's remaining contribution to **G-GPS** | Decision row; adversarial cases; payout integration + regression tests; independent money review. |
| 4 | **W0-02 — integrity conflict mapping** | PARENT | Map the four exclusivity constraint races to stable 409 envelopes (§6.4, §35 RM7). | W0-01 | Closes RM7 before pilot | Constraint tests and API envelopes; no unhandled `IntegrityError`. |
| 5 | **W0-03 — correction authority** | PARENT | Effective-dated immutable payout rules, correction orders, value-complete audit, and maker-checker approval (§16, §35 RM6). | W0-02 | Closes RM6's contribution to **G-money** | Migration/model/API/UI tests; historical-pricing and creator≠approver proofs; independent money/security review. |
| 6 | **W1-02 — fraud assessment, holds, disputes** | PARENT | Current per-trip assessment, authoritative non-terminal hold invariant, serialised review transitions, driver reasons/dispute, and minimal in-app notification (§17/§20, RM8; software controls from RM9). | W0-03; must precede S3 | Closes RM8's contribution to **G-money** and part of RM9 for **G-GPS** | State-transition, race, release-predicate, worker, API/UI, e2e, and independent money/concurrency review. |
| 7 | **W1-03A — release scheduling** | PARENT | Clean earnings release without a blanket delay; flagged earnings remain held under one RM8 predicate with a seven-day review SLA and no auto-release (§16.2, D18/Q22). | W1-02 | Satisfies the release-scheduling part of **G-money** | Time-boundary, escalation, no-auto-release, concurrency, retry, balance, worker, ops-UI tests, and independent money review. |
| 8 | **W1-03B — payout batches and reconciliation** | PARENT | Reservation/frozen payee/provider submission/line reconciliation plus carry-forward post-payment debt (§16.3, RM10/RM11, D18/Q27). | W1-03A + W0-03 | Closes RM10/RM11's contributions to **G-money** | Batch state-machine, uniqueness, instruction hash/idempotency, maker-checker, provider reconciliation, debt property tests, e2e, and independent money review. |
| 9 | **W2-00 — commercial money contracts** | PARENT | Advertiser company/profile management plus funded driver-liability authorization, effective-dated commercial terms, canonical receipt/allocation identity, audited production authority, cancellation cutoff/settlement, and atomic activation contracts (§15/§18/§21/§27, RM12/RM13, D20). | W1 complete | Defines how W2 closes RM12/RM13 for **G-commercial** | Reconciled design/invariants, migration plan, RBAC, concurrency/financial property tests, and independent architecture/money review. |
| 10 | **W2-01 — billing, invoices, payments** | PARENT | Per-campaign custom accepted terms, VAT-inclusive/itemised invoices, standard full-prepay plus approved-corporate credit, bank/gateway receipts, standard 24-hour production wait, audited expedited waiver, refunds and budgets (§15, D18/D20), built on W2-00. | W2-00; statutory company facts gate real issuance only | Partially closes **G-commercial**; real invoices remain blocked until company facts | Receipt dedup, amount/currency, webhook idempotency, invoice, production-authority/refund boundaries, budget, API/UI, e2e, and independent money review. |
| 11 | **W2-02 — secure files and KYC controls** | PARENT | Presigned storage, mandatory type/size/malware checks, purpose-scoped reads, encryption/key governance, and privileged-read audit (§12/§19, RM18). | Record storage/vendor decision before implementation | Closes RM18 for KYC/PWA pilot and contributes to **G-GPS/G-pilot** | Upload/download/security tests, audit evidence, retention/DSR coverage, and independent threat review. |
| 12 | **W2-03 — approvals, evidence, activation, cancellation** | PARENT | Campaign/creative/installation review; proof-of-display, device/vehicle binding, atomic activation, change requests, cancellation cutoff and settlement (§18/§19/§21, RM9/RM13). | W2-00/01/02 | Closes RM13 for **G-commercial** and remaining RM9 controls for **G-GPS** | Lifecycle/race tests, evidence review, cutoff clipping, settlement, API/UI, ops e2e, and independent review. |
| 13 | **W2-04 — notification and account-contact channels** | PARENT | Outbox-backed advertiser email and in-app triggers, password recovery, verified driver phone/consent; operations-run driver WhatsApp remains manual (§20/§23, Q34). | W1 notification core + W2 event sources | No independent gate; required MVP communication and recovery path | Retry/dedup/provider-receipt, token security, preference/consent, redaction, and user-flow tests. |
| 14 | **W3-00 — privacy and measurement foundation** | PARENT | DPIA/ROPA/roles/retention/DSR controls; central disclosure control; measurement methodology, immutable runs, uncertainty, proof-of-performance and the performance-report/conditional-ROI contract (§22/§24/§27, RM15/RM16, D20). | Qualified Nigerian legal/privacy review is required before live use, not before building controls | Closes RM15/RM16 contributions to **G-GPS/G-advertiser/G-moduleG** | Approved artefacts/runbooks, disclosure/differencing tests, reproducible performance and conditional-ROI fixtures, and independent privacy/measurement review. |
| 15 | **W3-01 — retargeting sources, segments, insights** | PARENT | Typed aggregate sources, campaign/zone linkage, exposure segments, controlled insights, export and gated geography/time/context activation with person-level payload rejection (§22, D6/D11/D18/D20/Q11). | W3-00; legal artifacts gate export and EXT-AD-PLATFORM gates live aggregate contextual activation | Implements **G-moduleG** subject to live-use gates | Privacy-boundary, provenance, suppression, schema rejection, export/activation approval, API/UI, e2e, and independent privacy review. |
| 16 | **W3-02 — exposure score and high zones** | PARENT | Versioned exposure metric and high-exposure zone views over reproducible measurement runs (§22.4/§27). | W3-00/01 | Implements the governed advertiser outputs behind **G-advertiser** | Formula fixtures, disclosure controls, reproducibility, report/UI tests, and independent measurement review. |
| 17 | **W3-03 — matching, offers, activity** | PARENT | Eligibility/scoring recommendations, admin assignment, driver offer response, inactive sweeps and flags (§21, Q7/Q20). | W2-03 activation/evidence | Required assignment/operations capability; no independent gate | Deterministic scoring, exclusivity/race, sweep, API/UI, and driver/admin e2e tests. |
| 18 | **W3-04 — driver self-registration and vehicle onboarding** | PARENT | Public application, secure document upload, bank/KYC and driver-owned vehicle-profile review before work (§23, Q13/Q23/Q26; proposal Module C). | W2-02 + W3-03 | Must preserve RM18 controls before KYC/vehicle use | Abuse/security, review-state, KYC/vehicle audit, API/UI, onboarding e2e, and independent security/privacy review. |
| 19 | **W4-01 — production driver PWA** | PARENT | Installable screen-on pilot client with fail-closed permissions/visibility, durable offline/retry sync, session safety, tracking health and the frozen backend contract (§23, D18). | RISK-01 + W1–W3 | Supplies the D18 PWA replacement for RM14's former native **G-pilot** gate and closes relevant RM15/RM18 contributions | Full Android/iOS browser/device matrix, battery/completeness SLOs, security review, and journey e2e. |
| 20 | **W4-02 — exports and issued reports** | PARENT | Remaining bounded CSV/PDF Campaign Performance Analysis package, with true ROI only behind the D20 data-and-method gate (§27/§30, D11/D20). | W3-00/01/02 | Governed by **G-advertiser/G-moduleG** | Performance/ROI golden files, access/privacy controls, reproducibility, load, UI tests, and independent privacy/measurement review. |
| 21 | **W4-03 — pilot deployment and readiness** | PARENT | Cardvert client-owned deployment, observability, restore/recovery, incident rehearsal, provider/permit gates and Abuja pilot acceptance (§25/§26, D18–D20/RM17). | All prior slices; registered external gates | Closes **G-pilot** only when every §35.3 gate passes | Staging burn-in, backup/restore, smoke/load/security evidence, provider/permit/legal approvals, and independent launch review. |
| 22 | **W4-04 — onboarding, training, handover** | PARENT | Role-based training, operator runbooks, support/handover and post-MVP roadmap promised by D11. | W4-03 release candidate | Final MVP delivery evidence, not a technical gate | Accepted materials, rehearsed operating flows, known-risk/deferment register. |

## Mandatory checklist item register

This register preserves the complete implementation detail from the reviewed
71-item decomposition. Each item belongs to exactly one package and remains a
binding acceptance obligation, but no row here is independently promoted or
requires a separate owner-facing review cycle. A checklist specification may
be refined inside its package without weakening its outcome, acceptance,
verification, gates or required specialist review.

| # | Checklist item | Package | Status | Observable outcome | Prerequisites |
| ---: | --- | --- | --- | --- | --- |
| 1 | **R14-A — production-PWA direction and protocol ADR** | PKG-01 | DONE | Executable evidence freezes installability, screen-on, permission, visibility, session, queue and seal semantics for the pilot PWA. | none |
| 2 | **R14-B — cross-profile interrupted-trip build proof** | PKG-01 | DONE | Desktop and mobile browser profiles prove the complete interrupted synthetic-trip contract; physical Android/iPhone route and battery runs remain deferred validation. | leaf: R14-A |
| 3 | **R17-A — production-like release/recovery build proof** | PKG-01 | DONE | Provider-neutral production-like topology, release smoke and recovery controls verify locally with synthetic data; external deployment remains deferred validation. | none |
| 4 | **FND-02A — stationary-time policy decision** | PKG-01 | DONE | Owner records a versionable rule separating traffic exposure from parked-time farming. | none |
| 5 | **FND-02B — stationary policy implementation** | PKG-01 | DONE | Classifier, fingerprints and earnings explanations implement the recorded rule. | leaf: FND-02A; external: EXT-RM2-POLICY |
| 6 | **FND-07 — exclusivity conflict envelopes** | PKG-01 | DONE | Four known assignment/trip races return stable 409 errors, not 500s. | none |
| 7 | **MNY-06A — immutable payout-rule revisions** | PKG-01 | DONE | Financial rule history becomes effective-dated, immutable and value-audited. | none |
| 8 | **MNY-06B — assignment/trip rule binding and payout_v3** | PKG-01 | DONE | Accepted driver terms freeze base/premium rates, zone/eligibility revisions and the `payout_v3` rule used by each interval/trip. | leaf: MNY-06A |
| 9 | **MNY-06C — maker-checker correction orders** | PKG-01 | DONE | Retroactive recompute requires a projected order and separate approver. | leaf: MNY-06B |
| 10 | **MNY-08A — current fraud assessments** | PKG-02 | DONE | Every sealed trip has one current pending/clean/flagged/error assessment. | none |
| 11 | **MNY-09A — cross-trip/account replay detection** | PKG-02 | DONE | Identical and time-shifted route replay becomes reviewable evidence. | leaf: MNY-08A |
| 12 | **MNY-08B — review states and hold invariant** | PKG-02 | DONE | One serialized transition table and hold predicate controls all money consumers. | leaf: MNY-08A, MNY-09A |
| 13 | **MNY-08C — driver reasons, disputes and in-app notice** | PKG-02 | DONE | Drivers can see holds, dispute them and receive sanitized outcomes. | leaf: MNY-08B |
| 14 | **MNY-03A — clean release and flagged review SLA** | PKG-02 | DONE | Clean entries release idempotently; flagged entries remain held for approve/decline with seven-day escalation and no auto-release. | leaf: MNY-08B |
| 15 | **MNY-10A — protected payee/account foundation** | PKG-02 | DONE | Payouts target an immutable payee and verified bank-account version safely. | none |
| 16 | **MNY-10B — batch reservation and provider submission** | PKG-02 | DONE | Available entries are atomically reserved into frozen, idempotent provider instructions and submitted only after maker-checker approval. | leaf: MNY-10A |
| 17 | **MNY-10C — provider line reconciliation and paid finality** | PKG-02 | DONE | Each automated transfer line reconciles from signed webhook/verified poll evidence before cash-paid finality. | leaf: MNY-10B |
| 18 | **MNY-11A — carry-forward post-payment debt** | PKG-02 | DONE | Later corrections reduce future pay without rewriting paid history. | leaf: MNY-10C, MNY-06C |
| 19 | **W2-00A — packages, custom quotes and accepted terms** | PKG-03 | DONE | A versioned custom quotation for every campaign—including an externally prepared quote recorded afterward—creates one immutable accepted snapshot; the legacy title does not authorize a launch package catalogue. | leaf: MNY-11A |
| 20 | **W2-00D — advertiser company profile management** | PKG-03 | DONE | Advertiser and admin manage tenant-safe company/contact details used by commercial surfaces. | none |
| 21 | **W2-00B — canonical receipts and allocations** | PKG-03 | DONE | One immutable external receipt can fund obligations once, within its amount. | leaf: W2-00A |
| 22 | **W2-01A — VAT-itemised invoices** | PKG-03 | DONE | Admin issues numbered immutable invoices; advertiser sees VAT-inclusive pricing with included net, VAT line and gross balance. | leaf: W2-00A, W2-00D |
| 23 | **W2-01B — manual bank-transfer confirmation** | PKG-03 | DONE | Ops reconciles transfers into the shared receipt/allocation/payment history. | leaf: W2-00B, W2-01A |
| 24 | **W2-00C — funded/approved-credit liability authorization** | PKG-03 | DONE | Standard work is fully prepaid and waits 24 hours before production; approved corporate credit remains bounded, while any expedited start requires an immutable advertiser waiver and audited actual start. | leaf: W2-01B, MNY-11A |
| 25 | **W2-01C — gateway adapter and webhook ingestion** | PKG-03 | BLOCKED — EXT-PAYMENT-PROVIDER | One-off Q3 checkout and signed provider events converge into canonical receipts. | leaf: W2-00B, W2-01A; external: EXT-PAYMENT-PROVIDER |
| 26 | **W2-01D — credits, reversals and 24-hour refund registry** | PKG-03 | DONE | Standard refund eligibility lasts to the 24-hour boundary; expedited eligibility ends only when production actually begins under an immutable advertiser-requested waiver. | leaf: W2-01A, W2-01B |
| 27 | **W2-01E — advertiser-spend budget enforcement** | PKG-03 | DONE | Spend facts drive persisted alerts/pauses without using driver payout cost as a proxy; live policy values remain externally gated. | leaf: W2-01A, W2-01B |
| 28 | **W2-02A — private object-storage foundation** | PKG-04 | DONE | Direct private uploads produce managed stored-file records; production adoption remains gated by EXT-STORAGE-PROVIDER. | none |
| 29 | **W2-02B — malware scanning and purpose-scoped reads** | PKG-04 | DONE | Unsafe files fail closed and privileged downloads are short-lived/audited; production adoption remains gated by EXT-MALWARE-SCANNER. | leaf: W2-02A |
| 30 | **W2-02C — advertiser creative upload** | PKG-04 | DONE | Campaign flows use managed scanned assets instead of arbitrary URLs; legacy URL rows remain readable but cannot authorize a new offer. | leaf: W2-02B |
| 31 | **W2-02D — encrypted KYC and financial identifiers** | PKG-04 | DONE | Required documents/NIN/bank data reuse the crypto port and are protected/version-reviewed; production custody remains gated by EXT-KMS-CUSTODY. | leaf: W2-02B, MNY-10A |
| 32 | **W2-02E — file/KYC lifecycle and incident operations** | PKG-04 | DONE | File/KYC purge plus scanner/key/vendor failures are tested and audited. | leaf: W2-02B, W2-02D |
| 33 | **W2-03A — campaign submission and approval** | PKG-04 | DONE | Advertiser submits; admin approves/rejects; unapproved campaigns cannot schedule. | none |
| 34 | **W2-03B — creative review gate** | PKG-04 | DONE | Only admin-approved, scan-cleared creative can satisfy campaign launch. | leaf: W2-02C |
| 35 | **W2-03C — installation evidence and proof-of-display** | PKG-04 | DONE | Assignment-bound evidence and nonce proof gate earning eligibility. | leaf: W2-02B |
| 36 | **W2-03D — atomic activation** | PKG-04 | DONE | One admin command locks/rechecks every commercial and operational prerequisite, including valid standard-wait or expedited-waiver production authority. | leaf: W2-00C, W2-01A, W2-01B, W2-03A, W2-03B, W2-03C |
| 37 | **W2-03E — governed mid-flight changes** | PKG-04 | DONE | Expansions honor funded headroom; reductions need approval and effective revisions. | leaf: W2-00A, W2-00C, W2-03D |
| 38 | **W2-03F — cancellation cutoff and settlement** | PKG-04 | DONE | One idempotent cutoff stops new work, clips pay and applies the standard-boundary or actual-waived-start refund rule. | leaf: W2-01D, W2-03D, MNY-11A |
| 39 | **W2-03G — proof challenges and spot checks** | PKG-04 | DONE | Missed challenges and physical verification feed the authoritative fraud hold. | leaf: MNY-09A, W2-03C, W2-03D |
| 40 | **W2-04A — notification core and role surfaces** | PKG-04 | DONE | W1 in-app notices become the shared outbox/list/unread-preference system. | leaf: MNY-08C |
| 41 | **W2-04B — advertiser email delivery** | PKG-04 | DONE | Worker-dispatched email and signed receipts update one logical notification; live delivery remains gated by EXT-EMAIL-PROVIDER. | leaf: W2-04A |
| 42 | **W2-04C — business triggers and manual driver contact** | PKG-04 | DONE | Stable event keys notify users; driver WhatsApp remains an audited ops task. | leaf: W2-04A, W2-04B, W2-01E, W2-03F, W2-03G, MNY-10C |
| 43 | **W2-04D — account recovery and verified contact preferences** | PKG-04 | DONE | Advertiser/admin password reset and driver verified-phone/WhatsApp consent are explicit; live pilot sends remain gated by EXT-PHONE-OPERATOR. | leaf: W2-04B, W2-04C |
| 44 | **W3-00A — privacy operating model** | PKG-05 | DONE | DPIA/ROPA/roles/lawful bases/consent/vendor/breach responsibilities are explicit. | none |
| 45 | **W3-00B — end-to-end retention and DSR** | PKG-05 | DONE | Synthetic DSR spans DB, objects, devices, logs, backups and processors. | leaf: W3-00A, W2-02E |
| 46 | **W3-00C — central disclosure-control service** | PKG-05 | DONE | Every advertiser heatmap/report/audience query enforces one privacy floor. | leaf: W3-00A |
| 47 | **W3-00D — measurement methodology contract** | PKG-05 | DONE | Product defines modelled potential contacts, provenance, uncertainty and claims; Campaign Performance Analysis is standard and true ROI requires approved inputs and method. | none |
| 48 | **W3-00E — immutable measurement runs and proof manifests** | PKG-05 | DONE | Issued results bind frozen inputs to creative/evidence/assignment/period and reproduce whether the ROI gate passed or failed closed. | leaf: W3-00D, W2-03C, W2-03D |
| 49 | **W3-01A — typed retargeting source registry** | PKG-05 | DONE | Advertiser/admin manage allowlisted aggregate planning sources without identifiers. | leaf: W3-00A, W3-00D |
| 50 | **W3-01B — source/campaign/zone linkage** | PKG-05 | DONE | Owned sources link safely to campaigns, zones and time windows. | leaf: W3-01A |
| 51 | **W3-01C — governed exposure segments** | PKG-05 | DONE | Worker materializes versioned, suppressed coverage-cell/time aggregates. | leaf: W3-00C, W3-00D, W3-00E, W3-01B |
| 52 | **W3-01D — recommendations, export and gated activation** | PKG-05 | DONE | Safe geography/time/context recommendations, controlled export and activation use one governed aggregate; identifiers/person-level payloads reject and live push fails closed without EXT-AD-PLATFORM. | leaf: W3-01C, W3-00D, W3-00E |
| 53 | **W3-02A — exposure score v1** | PKG-05 | DONE | Formula-versioned score is reproducible and distinct from impressions. | leaf: W3-00D, W3-00E |
| 54 | **W3-02B — high-exposure zone insights** | PKG-05 | DONE | Governed ranked zones appear in admin/advertiser maps and reports. | leaf: W3-00C, W3-00E |
| 55 | **W3-03A — matching recommendations** | PKG-06 | DONE | Admin receives deterministic eligible driver/vehicle rankings. | none |
| 56 | **W3-03B — complete offer lifecycle** | PKG-06 | DONE | Terms-complete expiring offers support accept/decline and immutable evidence. | leaf: W3-03A, W2-00A, MNY-06B |
| 57 | **W3-03C — activity floor and inactivity handling** | PKG-06 | DONE | Verified-hours/inactivity sweeps create reviewable ops flags and notices. | leaf: W3-03B, W2-04A |
| 58 | **W3-04A — public driver application** | PKG-06 | DONE | Abuse-resistant registration creates a pending, non-work-eligible application. | none |
| 59 | **W3-04B — KYC/bank onboarding approval** | PKG-06 | DONE | Person/payee KYC is approved but remains non-work-eligible pending W3-04C vehicle approval. | leaf: W3-04A, W2-02D, MNY-10A |
| 60 | **W3-04C — driver vehicle profile and approval** | PKG-06 | DONE | Identity/KYC-approved applicants add vehicle evidence; admin approval grants work eligibility. | leaf: W3-04B, W2-02B, W2-02D |
| 61 | **W4-01A — PWA foundation and session security** | PKG-07 | DONE | The installable production client uses the BFF session safely and fails closed on unsupported permission/storage/lock states. | leaf: R14-A, R14-B; external: EXT-PKG07-OWNER-RELEASE |
| 62 | **W4-01B — screen-on tracking and durable sync** | PKG-07 | DONE | Explicit Start/End tracking survives reload/network interruption, reports visibility degradation and never claims unsupported background capture. | leaf: W4-01A, R14-B |
| 63 | **W4-01C — PWA onboarding and campaign journey** | PKG-07 | DONE | Onboarding, vehicle, offers, activation and tracking integrate through governed BFF/API contracts. | leaf: W4-01B, W3-04C, W3-03B, W2-03D |
| 64 | **W4-01D — PWA earnings, disputes and release rehearsal** | PKG-07 | DONE | History, earnings, disputes, notifications, installability and production-PWA release evidence are complete. | leaf: W4-01C, MNY-08C, MNY-11A, W2-04A, W2-04C |
| 65 | **W4-02A — governed maps and report experience** | PKG-08 | DONE | Existing maps/reports consume safe runs; performance analysis is standard and ROI is absent unless its data/method gate passes. A production basemap remains a live-release gate, not a provider-neutral build prerequisite. | leaf: W3-00C, W3-00D, W3-00E, W3-01D, W3-02A, W3-02B |
| 66 | **W4-02B — bounded CSV/PDF issuance** | PKG-08 | DONE | Async hashed exports reproduce the frozen performance/conditional-ROI decision and honor privacy/legal gates. | leaf: W4-02A |
| 67 | **W4-03A — client-owned release environment** | PKG-08 | BLOCKED — EXT-RELEASE-ENV, EXT-STAGING-APPROVAL | Provider-neutral deployment/recovery preparation is exhausted; DONE still requires an approved account/domain hosting a hardened release candidate plus live staging recovery validation. | leaf: R17-A, W4-01D, W4-02B; external-live: EXT-RELEASE-ENV, EXT-STAGING-APPROVAL |
| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 | BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS | Synthetic acceptance machinery is complete; DONE still requires every §35 gate and the controlled Abuja journey, including approved providers, contextual activation, performance/conditional-ROI reporting, automated transfer, deployment and permit evidence. | leaf: W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS |
| 69 | **W4-04A — role-based onboarding and training** | PKG-09 | BLOCKED — EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-OPERATIONS-OWNER | Provider-neutral role-task and operator preparation is exhausted; DONE still requires rehearsal with approved users and the named operations owner against the release candidate. | leaf: W4-01D, W4-02B; external-live: EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-OPERATIONS-OWNER |
| 70 | **W4-03C — controlled pilot and stabilization** | PKG-09 | BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER | Provider-neutral telemetry, rollback, replay, incident and evidence preparation is exhausted; DONE still requires approved users to run a monitored controlled pilot. | leaf: W4-01D, W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER |
| 71 | **W4-04B — handover, support and roadmap closure** | PKG-09 | BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER, EXT-BRAND-APPROVAL | Provider-neutral handover, support and roadmap preparation is exhausted; DONE still requires named-owner acceptance, release/brand approval and credential handover after the controlled pilot. | leaf: W4-01D, W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS, EXT-OPERATIONS-OWNER, EXT-BRAND-APPROVAL |

## Checklist item specifications

Every card below is binding at outcome level. Before implementation, the active
agent expands the card into the delivery contract required by root AGENTS.md
and obtains the named independent reviews. Shared public contracts, schemas,
migrations, auth, money state, privacy controls and global lifecycle changes
remain single-owner and serialized.

Legacy names are aliases only: **S2** ≈ MNY-08A/B/C + MNY-09A; **S3** ≈
MNY-03A + MNY-10A/B/C + MNY-11A; **S5** ≈ the W2-01A billing opener. These
names never authorize work or replace the package queue.

### Early risk, W0 and W1

#### R14-A — production-PWA direction and protocol ADR

- **Scope / authority:** define the supported Android/iOS browser/device matrix,
  installability, screen-on/visibility contract, staged geolocation permission,
  BFF session posture, D15/D16 IndexedDB/Web Locks queue/seal compatibility and
  visible `active/degraded/stopped` health (§23, D18/RM17, Q10). Native
  background execution, native secure credentials and store release are Phase 2.
- **Acceptance:** ADR freezes the PWA threat/protocol/test matrix, names
  supported/rejected browser states and introduces no silent API/auth break.
- **Verify / review:** OpenAPI/BFF contract fixtures plus deterministic browser
  capability, denial and revocation probes and independent PWA/security/
  architecture review. Representative Android/iPhone execution is a D23
  post-build validation gate and is never claimed by this build proof.

#### R14-B — cross-profile interrupted-trip build proof

- **Scope / authority:** the installable PWA proves explicit Start/End,
  screen-on enforcement, permission and visibility degradation, durable
  IndexedDB queue, Web Locks single-writer, stable retry keys, seal watermark
  and BFF session recovery (§23, D18/RM17, D15/D16). Synthetic routes only.
- **Acceptance:** no acknowledged batch is lost/duplicated; desktop and mobile
  browser profiles show that reload, offline,
  permission revocation, storage/lock failure or screen/background transition
  recovers or fails closed visibly through trip→seal→worker payout. Physical
  device/browser completeness, latency, route accuracy and four-hour battery
  measurements remain incomplete post-build validation.
- **Verify / review:** deterministic capability/queue/tracker tests, desktop and
  mobile browser-profile synthetic journey, backend seal/payout integration and
  independent PWA/security/data-loss review. D23 defers, but does not waive,
  the representative physical-device matrix before real pilot use.

#### R17-A — production-like release/recovery build proof

- **Scope / authority:** verify the existing edge/API/frontend/PostGIS/Redis/
  worker topology, typed secret contract, migrations, queue-loss recovery,
  rollback design, observability, release smoke and database restore controls
  in a provider-neutral production-like build (§25, §31, RM17, Q32). Do not
  deploy externally or invent account/spend approval. The completed build proof
  did not execute a frontend-image rollback.
- **Acceptance:** production compose and edge configuration resolve, release and
  backup/restore safety contracts pass with synthetic data, and the sealed-trip
  worker path remains covered; no personal data or external environment claim.
- **Verify / review:** deterministic pre-production configuration, smoke,
  migration, worker-recovery and restore tests plus deployment/security review;
  frontend-image rollback is `NOT RUN — PKG02-C3` until its image reference is
  parameterized and the rollback is exercised before W4-03A.
  Approved-environment deployment, public-edge evidence and a live restore drill
  remain explicit D23 post-build validation before W4 release/pilot.

#### FND-02A — stationary-time policy decision

- **Scope / authority:** owner selects rolling displacement, cumulative
  sub-window budget or explicit fraud deferral; records parameters, effective
  timing, traffic/farming examples and D14 version consequence (§16.1, RM2,
  D2/D4/D9/D14, Q5). No code or invented thresholds.
- **Acceptance:** a decision-log row and executable fixture table fully define
  both honest congestion and stop-hop farming behavior.
- **Verify / review:** independent product/money review of the fixture table.

#### FND-02B — stationary policy implementation

- **Scope / authority:** implement FND-02A in eligibility classification,
  typed settings/rule overlays, money fingerprints and relevant admin/driver
  explanations. Excludes other fraud rules and production-PWA tracking.
- **Acceptance:** the known stop-4:59/hop pattern cannot farm pay; honest
  traffic matches the decision; eligible + excluded equals session duration;
  historical money remains reproducible.
- **Verify / review:** property/unit, PostGIS payout/recompute, driver UI/e2e
  tests; independent money review.

#### FND-07 — exclusivity conflict envelopes

- **Scope / authority:** map the four built vehicle/assignment/driver/trip
  exclusivity constraints to service-specific standard 409 envelopes (§6.4,
  RM7, D13, Q16). Do not redesign exclusivity.
- **Acceptance:** every losing race returns a stable code/message/request ID;
  unrelated integrity failures remain unexpected.
- **Verify / review:** classifier, concurrent assignment/trip and HTTP tests;
  API/concurrency review.

#### MNY-06A — immutable payout-rule revisions

- **Scope / authority:** replace in-place financial mutation with immutable
  effective-dated revisions, create/supersede APIs/UI and value-complete audit
  (§16.1, RM6, D9/D14, Q4/Q5/Q22).
- **Acceptance:** issued revisions cannot edit or overlap; history stays
  readable; every change records before/after values and reason.
- **Verify / review:** migration/model/API/UI/effectiveness/concurrency tests;
  independent money/security review.

#### MNY-06B — assignment/trip rule binding and `payout_v3`

- **Scope / authority:** add `payout_v3`; freeze accepted base/premium rates,
  cap, zone and eligibility revisions on assignment; each interval resolves
  base outside the premium target zone, premium inside, or a configured unpaid
  exclusion/invalid reason (§16.1/§21, RM6, D18/Q4/Q5). `payout_v1/v2` history
  stays immutable. W3 recommendation/offer redesign remains later.
- **Acceptance:** later revision never reprices accepted work; accept-vs-revise
  races are deterministic; payout fingerprint records all bindings; reports
  explain tier/reason and formula version; the D22 stationary marker and
  complete resolved values freeze at acceptance and unknown markers fail closed.
- **Verify / review:** acceptance→trip→payout integration, race and driver e2e;
  money/architecture/concurrency review.

#### MNY-06C — maker-checker correction orders

- **Scope / authority:** named adjuster creates projected correction order;
  separate approver submits/rejects/executes it; positive deltas remain pending
  with their own release date (§16.1/16.2, RM6, Q22).
- **Acceptance:** creator cannot approve; stale projection re-reviews;
  execution is idempotent; old/new values, reason and actors are audited.
- **Verify / review:** permission, delta, DB constraint, concurrency/retry and
  admin e2e; independent money/security review.

#### MNY-08A — current fraud assessments

- **Scope / authority:** add per-sealed-trip pending/clean/flagged/error
  assessment with version/fingerprint/currentness and convergent worker retry
  (§14/§17, RM8, Q21). Excludes UI/release.
- **Acceptance:** exactly one current successful assessment is required;
  changed inputs make it stale; failure stays error, never silently clean.
- **Verify / review:** migration, fingerprint/state and worker error/idempotency
  tests; money/concurrency review.

#### MNY-09A — cross-trip/account replay detection

- **Scope / authority:** canonical route/payload fingerprints detect identical
  and time-shifted replays across trips/accounts with configurable tolerance
  (§17, RM9, D13). Excludes device proof and physical spot checks.
- **Acceptance:** known replay fixtures flag explainably; legitimate distinct
  routes do not; same-trip idempotent replay is excluded.
- **Verify / review:** deterministic/property/PostGIS/scale tests; independent
  fraud/privacy review.

#### MNY-08B — review states and hold invariant

- **Scope / authority:** serialized acknowledge/confirm/dismiss lifecycle,
  reviewer evidence and one shared hold_active predicate for every money
  consumer (§16.2/§17, RM8, Q21/Q22).
- **Acceptance:** open/acknowledged/unresolved-confirmed stay held; only
  dismissed releases; illegal transitions and review/release races fail safely;
  a minimum-payout floor or second consumer predicate cannot restore held pay.
- **Verify / review:** transition, DB-race, payout/impression/release and admin
  e2e tests; independent money/concurrency review.

#### MNY-08C — driver reasons, disputes and in-app notice

- **Scope / authority:** sanitized hold reasons/status, dispute/reply lifecycle
  and transactional deduped in-app notifications (§17/§20, Q21/Q34). Excludes
  email, automated WhatsApp/SMS and push.
- **Acceptance:** only the owning driver accesses/disputes; internal evidence
  remains private; retry creates one dispute/notice; resolution notifies.
- **Verify / review:** authorization/redaction/API/worker and driver/admin e2e;
  privacy/security review.

#### MNY-03A — clean release and flagged review SLA

- **Scope / authority:** DB-derived idempotent sweep makes current-clean,
  unheld pending entries available without a blanket delay; suspected/flagged
  entries remain pending for named-admin approve/decline with a seven-day SLA
  and escalation (§14.3/§16.2, RM8, D18/Q22). Weekly cadence batches transfers;
  no hard-coded weekday and no timed auto-release.
- **Acceptance:** clean, held, dismissed and exact seven-day boundaries are
  deterministic; retry/concurrency move once; stale/error or active hold blocks;
  unresolved day-seven entries remain held and visibly escalated; corrections
  honor their own review state.
- **Verify / review:** frozen-time, balance, worker-twice, concurrency and ops
  UI e2e; independent money review.

#### MNY-10A — protected payee/account foundation

- **Scope / authority:** versioned payee abstraction with driver as pilot
  default, verified bank-account snapshot, privileged-read audit, and D17's
  shared crypto-provider port (`encrypt/decrypt/rotate`, key-version stamped per
  encrypted value) (§16.3, RM10/RM18, Q23/Q26/Q27). Pilot key custody is a
  required typed-Settings KEK with no default; excludes fleet behavior, full
  KYC and live verification provider.
- **Acceptance:** payout line freezes payee/account version; authenticated
  per-record envelope encryption records algorithm/key version and binds
  tenant/record/field as associated data; plaintext never reaches DB, list APIs,
  logs, audit payloads, exports, or errors; future fleet payee is data-only.
- **Verify / review:** ciphertext inspection, wrong-associated-data/failure,
  redaction/RBAC/migration/rotation/rewrap tests and synthetic driver flow;
  independent money/security review.

#### MNY-10B — batch reservation and provider submission

- **Scope / authority:** draft→reserved→submitted batch, atomic one-active-line
  reservation, frozen payee/account/amount/instruction hash, stable idempotency
  key, approved disbursement adapter and maker-checker before submission
  (§16.3, RM10, D18/Q22/Q23/Q27). Provider-neutral tests do not require live
  credentials.
- **Acceptance:** concurrent runs cannot double-reserve; total equals lines;
  exported snapshot is immutable and any prior change invalidates its hash.
- **Verify / review:** uniqueness/concurrency/property/instruction-hash,
  retry-idempotency, fake-provider/API/UI tests; independent money/security review.

#### MNY-10C — provider line reconciliation and paid finality

- **Scope / authority:** submitted→reconciled/completed|failed|void with unique
  provider line reference, signed webhook or verified polling, partial
  failure/idempotent retry and separate reconciler (§16.3, RM10, D18/Q27).
  `EXT-DISBURSEMENT-PROVIDER` gates financially effective submission.
- **Acceptance:** no batch-level assertion marks cash paid; failed lines stay
  unpaid/retryable; completion requires every line resolved; void safely
  releases reservations.
- **Verify / review:** state, duplicate reference, partial failure, retry and
  pilot-form e2e; independent money/security review.

#### MNY-11A — carry-forward post-payment debt

- **Scope / authority:** explicit earned-net/released/cash-paid/debt/
  batch-payable balances allocate later reversals against future credit
  (§16.2/16.3, RM11, Q22/Q27). No collections or negative transfer.
- **Acceptance:** reversal never increases balance; paid history is immutable;
  future credit clears debt before becoming batchable; currencies never mix.
- **Projection boundary:** economic/provenance totals retain every non-voided
  source and subtract reversals, while `debt_remainder` contributes zero.
  Settlement totals separately report released credit, cash paid, carried debt
  and debt-aware batch-payable amount; status changes made for allocation do
  not rewrite economics.
- **Verify / review:** cross-payment-boundary property and multi-period
  recompute→debt→batch e2e; independent money review.

### W2 commercial and operations

#### W2-00A — packages, custom quotes and accepted terms

- **Scope / authority:** versioned custom-quote request/record/accept path for
  every campaign and immutable accepted campaign snapshot with
  line/tax/production-cost/payment-class terms (§15.1/15.2, D18/Q1/Q2/Q14/Q25).
  An externally agreed quote/deal is recorded afterward as the same accepted
  terms, never as an unstructured note. A package catalogue is not launch
  scope. Excludes generated quote PDFs and public advertiser self-registration.
- **Acceptance:** every campaign has one accepted custom-quotation revision;
  accepted terms never mutate; advertiser ownership/RBAC and effective dates hold.
- **Verify / review:** migration/effective-date/mutation/cross-org tests and
  admin→advertiser acceptance e2e; architecture/money review.

#### W2-00D — advertiser company profile management

- **Scope / authority:** advertiser-owned company name, address, industry and
  operational/billing contacts are viewable/editable through tenant-safe
  advertiser and admin surfaces (proposal Module B/Month 2, §27). Separate
  these tenant facts from the platform issuer facts supplied under Q28.
- **Acceptance:** permitted fields and admin-only fields are explicit; cross-org
  reads/writes fail; changes audit before/after values; billing/campaign views
  consume the canonical organization record rather than copy it.
- **Verify / review:** schema/API/RBAC/audit/form-validation and advertiser↔admin
  e2e; authorization/privacy/commercial review.

#### W2-00B — canonical receipts and allocations

- **Scope / authority:** immutable receipt identity/evidence with unique
  external transaction ID, amount/currency/payer, observed→reconciled→
  confirmed|reversed lifecycle and separate allocation rows (§15.2–15.4,
  RM13a, Q2/Q3).
- **Acceptance:** one receipt cannot overfund or double-fund; mismatch cannot
  confirm; only confirmed allocations grant authority; reversal records cutoff.
- **Verify / review:** uniqueness/allocation-sum/row-lock/reversal property and
  admin reconciliation e2e; independent money/fraud/concurrency review.

#### W2-01A — VAT-itemised invoices

- **Scope / authority:** per-scope numbering, VAT-inclusive customer display
  with itemised included net, VAT amount and gross total, standard
  full-prepayment or immutable approved
  corporate-credit obligations, immutable issuance/correction rule, admin and
  advertiser billing surfaces (§15.1/15.2, D18/Q2/Q14/Q28).
- **Acceptance:** decimal/currency invariants; issued rows do not mutate;
  numbering is concurrency-safe; status derives from confirmed allocations;
  placeholder company facts cannot issue a real invoice.
- **Verify / review:** numbering/migration/VAT golden/RBAC/API and draft→issue→
  view e2e; independent money/accounting review.

#### W2-01B — manual bank-transfer confirmation

- **Scope / authority:** ops records/reconciles bank transfer, evidence and
  allocation; both parties see auditable payment history (§15.2/15.3, RM13a,
  D18/Q2/Q3). Standard production requires full confirmed funding; partial
  allocations remain visible but unauthorised. No bank API.
- **Acceptance:** over/under/partial cases are explicit; confirmation is
  idempotent; funding changes only from confirmed allocations; tenant isolation.
- **Verify / review:** invoice/allocation state, duplicate/mismatch adversarial
  tests and admin→advertiser e2e; independent money/permissions review.

#### W2-00C — funded liability authorization

- **Scope / authority:** immutable funded amount or approved-corporate credit
  authorization, subsidy, maximum driver liability and rate×cap×vehicle-day
  reserve/headroom with pending_funding state (§15/§16.1/§21, RM12,
  D18/D20/Q2/Q4/Q9/Q24). Credit approval snapshots limit, due date, approver
  and terms. Standard-prepaid production authority starts only at the exact
  24-hour boundary; expedited authority requires an immutable, versioned and
  audited advertiser-requested waiver, with actual production start recorded
  separately.
- **Acceptance:** liability differs from advertiser spend; concurrent activation
  cannot over-reserve; valid work remains payable after exhaustion; interval
  resolves then-effective terms; no production begins before valid authority.
- **Verify / review:** concurrency/property/effective-date/recompute/API/UI and
  exact-boundary/waiver/actual-start activation rejection e2e; independent
  money/architecture review.

#### W2-01C — gateway adapter and webhook ingestion

- **Scope / authority:** payment provider port, fake/manual adapter, selected
  provider checkout/verify, signed public webhook event log and async worker
  (§13–15.4, Q3, RM13a). Live adapter awaits provider/account decision.
- **Acceptance:** bad signature rejects; duplicate event is a no-op; request
  path only records/enqueues; retry converges to one receipt/allocation.
- **Verify / review:** signature/replay/enqueue/worker idempotency and sandbox
  simulation when credentials exist; security/money/deployment review.

#### W2-01D — credits, reversals and 24-hour refund registry

- **Scope / authority:** append-only invoice correction, receipt reversal and
  refund/settlement reference with adjusted advertiser balance. Eligibility
  normally runs to the exact 24-hour boundary from the first confirmed cash
  allocation authorising production. An expedited advertiser-requested waiver
  ends eligibility only when production actually begins; waiver acceptance
  alone does not. Corporate credit with no cash uses contract settlement, not
  a refund (§15.2/15.6, RM13a/b, D18/D20/Q24). Automatic execution is out.
- **Acceptance:** reversal never increases funding; original invoice/receipt
  remains; external refund reference is unique; refund cannot exceed authority;
  exact-before/at/after-24-hour, waiver-before-start, waived-start and
  no-cash-credit boundaries are deterministic.
- **Verify / review:** issue/pay/reverse/refund balance properties, duplicate
  races and API/UI e2e; independent money/accounting review.

#### W2-01E — advertiser-spend budget enforcement

- **Scope / authority:** billing-derived spend, configured threshold evaluation,
  persisted admin-visible threshold state, pause via the campaign service,
  idempotent worker and admin override/audit (§15.5, Q1/Q9). W2-04C alone owns
  alert delivery. Exact thresholds/timing need the recorded external policy;
  no predictive optimization.
- **Acceptance:** spend never proxies driver liability; retry does not duplicate
  threshold state or transitions; pause uses the campaign service; no hard
  delete or direct notification send.
- **Verify / review:** frozen-time/threshold/concurrent-payment tests and
  campaign e2e; money/worker/user-messaging review.

#### W2-02A — private object-storage foundation

- **Scope / authority:** storage port, local MinIO/provider adapter, presigned
  POST conditions, checksum/existence confirmation, private stored-file record
  and orphan lifecycle (§19/§25, RM18, Q18/Q26/Q32).
- **Acceptance:** no DB blobs/container files/public objects; expired,
  wrong-type, oversize or checksum-mismatch confirmation fails; tenants isolate.
- **Verify / review:** adapter/policy/CORS/confirm/replay/cleanup and upload
  simulation; independent threat/deployment/data-loss review.

#### W2-02B — malware scanning and purpose-scoped reads

- **Scope / authority:** server MIME/size validation, mandatory malware scan,
  quarantine/clear lifecycle, fail-closed review gates, short-lived purpose/
  reason GET and privileged-read audit (§12/§19, RM18).
- **Acceptance:** unscanned/infected/spoofed files cannot approve/download;
  URL expires; every privileged read records actor/subject/purpose/request.
- **Verify / review:** malware/MIME/oversize/retry/dedupe/URL/RBAC/audit tests;
  independent security/privacy/incident review.

#### W2-02C — advertiser creative upload

- **Scope / authority:** existing campaign wizard/detail uses managed scanned
  stored files with progress/retry and safe legacy-read compatibility
  (§19.2/19.3, Q18, D7/D11). Approval remains W2-03B.
- **Acceptance:** advertiser cannot claim ready/approved; scan failure is
  actionable; cross-org access fails; legacy URL cannot bypass launch gates.
- **Verify / review:** schema/actions/failure/retry/browser e2e; security/UX/
  backward-compatibility review.

#### W2-02D — encrypted KYC and financial identifiers

- **Scope / authority:** licence/registration/insurance/NIN/photos/agreement/
  bank linkage, versioned review, masking and purpose-authorized reveal using
  the same D17 crypto port/ciphertext schema introduced by MNY-10A (§19.3,
  RM18, Q26/Q27). Add the provider-neutral custody backend/adapter seam; the
  selected production KMS/vault remains an external adoption gate. Do not
  create a second crypto mechanism.
- **Acceptance:** sensitive data is never plaintext in DB/API/logs; every value
  retains algorithm/key version/associated-data binding; KMS/vault migration
  changes key custody, not ciphertext schema, and includes a safe rewrap/
  re-encryption path; rejected/expired docs block approval; reads are audited.
- **Verify / review:** ciphertext compatibility, pilot-key→KMS rewrap and
  recovery, rotation/masked serialization/RBAC/read-audit/document-state e2e;
  independent privacy/KMS review.

#### W2-02E — file/KYC lifecycle and incident operations

- **Scope / authority:** file/KYC-specific retention and object/link purge;
  key-loss, scan-outage and storage-vendor failure handling; and closure of the
  D10(g) auth/profile/assignment audit gaps (§12/§19, RM18, D10). Whole-platform
  ROPA, breach register and end-to-end DSR belong only to W3-00A/B.
- **Acceptance:** purge leaves no public/orphaned object; KYC/financial retention
  exceptions are explicit; unsafe scanner/key/provider states fail closed;
  every named privileged mutation/read is audited.
- **Verify / review:** file/KYC retention dry run, key-loss/scan/vendor outage
  simulation and route-audit coverage; independent privacy/security/operations
  review.

#### W2-03A — campaign submission and approval

- **Scope / authority:** guarded draft→pending_review→approved path, reasoned
  rejection, admin queue and advertiser history (§18, Q6). Replace direct
  advertiser scheduling/activation; no parallel approval flag.
- **Acceptance:** advertiser cannot self-approve/launch; rejection is an action
  with reason; all transitions audit and serialize.
- **Verify / review:** enum/migration/state/race/RBAC and submit→review e2e;
  authorization/lifecycle review.

#### W2-03B — creative review gate

- **Scope / authority:** scanned creative pending_review→approved|rejected,
  revision/resubmission and admin queue (§18/§19, RM13c, Q18).
- **Acceptance:** advertiser cannot set review state; history remains; unsafe,
  rejected or replaced asset cannot satisfy launch.
- **Verify / review:** transition/RBAC/race and upload→scan→submit→review e2e;
  security/lifecycle/audit review.

#### W2-03C — installation evidence and proof-of-display

- **Scope / authority:** assignment-bound installation revisions, admin review,
  vehicle/device metadata and server-nonce start-of-shift proof with expiry/
  renewal (§18/§19/§21, RM9/RM13c, Q15/Q17).
- **Acceptance:** evidence binds exact assignment/vehicle; stale/rejected/
  missed proof blocks activation/earning; nonce cannot replay; reads audit.
- **Verify / review:** binding/replay/expiry/race and driver→admin e2e;
  independent fraud/security/privacy review.

#### W2-03D — atomic activation

- **Scope / authority:** named admin command locks/rechecks funding, liability,
  accepted terms, standard-wait or expedited-waiver production authority,
  creative, assignment, vehicle, evidence and exclusivity; stores immutable
  snapshot; trip start rechecks it (RM12/RM13c, D20/Q15–Q17/Q24).
- **Acceptance:** no TOCTOU race or driver self-activation bypass; failed-gate
  checklist is explicit; reversal/cutoff invalidates authority correctly.
- **Verify / review:** full gate matrix, activation-vs-funding races, snapshot
  immutability and admin→driver trip e2e; money/architecture/fraud review.

#### W2-03E — governed mid-flight changes

- **Scope / authority:** effective-dated change request, impact preview and
  classification; expansions consume funded headroom or wait; reductions/
  removals/date changes need admin reason (§15.5/§18/§21, RM12, Q9).
- **Acceptance:** accepted history stays immutable; concurrent funding/change
  cannot overauthorize; interval resolves the revision then in force.
- **Verify / review:** expansion/reduction/date/headroom/recompute and UI e2e;
  independent money/architecture/concurrency review.

#### W2-03F — cancellation cutoff and settlement

- **Scope / authority:** idempotent campaign lock sets immutable financial
  cutoff, stops assignments/new work, clips payable intervals, releases
  liability and appends settlement/refund revisions under W2-01D's standard
  boundary or actual-waived-production-start rule (§15/§18/§21, RM13b,
  D18/D20/Q24).
- **Acceptance:** every ingestion/classification/recompute/release path honors
  one cutoff; pre-cutoff hours pay; repeated command converges; refund ref is
  unique and never created after the applicable eligibility cutoff.
- **Verify / review:** boundary/property/cancel-vs-trip/release races and full
  cancellation e2e; independent money/concurrency/data-loss review.

#### W2-03G — proof challenges and spot checks

- **Scope / authority:** configurable high-earner evidence renewal, missed
  challenge/concurrent-session day hold, physical spot-check queue/result and
  audit, consuming MNY-09A evidence (§17/§19/§21, RM9).
- **Acceptance:** hold uses MNY-08B state machine; dismissal/release is
  authoritative; no claim that phone GPS proves the branded vehicle moved.
- **Verify / review:** synthetic challenge/false-positive/worker/hold-release
  and ops e2e; independent fraud/money/privacy review.

#### W2-04A — notification core and role surfaces

- **Scope / authority:** extend MNY-08C into shared outbox with status/attempt/
  provider IDs, transactional typed creator, list/read/preferences and polled
  unread badge for all roles (§20/§27, Q34). No WebSocket/SSE/push.
- **Acceptance:** business mutation and row are atomic; dedupe works; tenant/
  RBAC isolation holds; frontend uses BFF polling.
- **Verify / review:** rollback/dedupe/read/polling and role e2e; privacy/
  concurrency/frontend-architecture review.

#### W2-04B — advertiser email delivery

- **Scope / authority:** email port/adapter, typed templates, worker retry/
  backoff, sender configuration and signed delivery receipt (§15.4/§20, Q34).
  Live provider awaits account/domain; no marketing email.
- **Acceptance:** no inline provider call; one logical send across retries;
  provider ID unique; receipt cannot mutate another message; payload redacts.
- **Verify / review:** adapter/retry/dedupe/signature/replay and sandbox send
  where possible; security/privacy/delivery review.

#### W2-04C — business triggers and manual driver contact

- **Scope / authority:** assignment, approval, funding, budget, cancellation,
  evidence, fraud and payout events create typed deduped notifications; driver
  WhatsApp becomes an auditable manual ops task (§20.2, Q34, RM18).
- **Acceptance:** retry cannot double-notify; failure is visible; manual contact
  completion is recorded; no KYC/bank/raw-route data enters message/log.
- **Verify / review:** per-trigger transaction/redaction/failure/retry/manual
  completion e2e; privacy/operations/money-event review.

#### W2-04D — account recovery and verified contact preferences

- **Scope / authority:** advertiser/admin password reset uses single-use,
  expiring, rate-limited email tokens. Driver phone verification follows the
  §20.3 pilot flow: server creates a hashed short-lived challenge and ops work
  item; ops manually sends the code to the claimed number; the driver enters it
  in-product. Versioned WhatsApp opt-in/withdrawal then authorizes manual contact
  (§20/§23/§30, Q34). Automated WhatsApp/SMS remains post-MVP.
- **Acceptance:** tokens are hashed, one-use and non-enumerating; password reset
  revokes existing sessions; phone challenges are rate/attempt limited, expire,
  record sender/channel/timestamps without storing plaintext codes, and verify
  only the claimed phone version; unverified or withdrawn numbers cannot create
  a normal manual-contact task; consent history is auditable and purpose-limited.
- **Verify / review:** expiry/replay/enumeration/rate-limit/session-revocation,
  phone/consent transitions and role e2e; independent auth/security/privacy
  review.

### W3 reach and measurement

#### W3-00A — privacy operating model

- **Scope / authority:** DPIA, ROPA, controller/processor allocation,
  purpose/lawful-basis matrix, subprocessor/region and breach registers,
  consent/notice versioning and withdrawal procedure (§22/§24, RM15, Q31).
  Final client legal wording and live data remain out.
- **Acceptance:** every purpose/data class has owner, basis, retention and
  recipients; withdrawal and breach escalation are rehearsed.
- **Verify / review:** document cross-check and tabletop; qualified Nigerian
  privacy/legal review required before live use.

#### W3-00B — end-to-end retention and DSR

- **Scope / authority:** per-class retention and tested access/rectification/
  erasure process spanning DB, object storage, device queue, logs, backups and
  processors (§24.2, RM15/RM18, Q31). No automated DSR portal.
- **Acceptance:** synthetic request leaves traceable evidence without deleting
  required ledger/audit facts; every exception/location is documented.
- **Verify / review:** DSR dry run plus backup/object/device/provider checks;
  independent privacy/data-loss/operations review.

#### W3-00C — central disclosure-control service

- **Scope / authority:** one service gates existing heatmap, future audience
  queries, reports and exports with coarse buckets, minimum vehicles/trips/
  days, contributor caps, complementary suppression, restricted filters,
  query history and differencing defense (§22.2, RM15).
- **Acceptance:** no caller bypass; current advertiser heatmap remains disabled
  until migrated; thresholds remain config pending pilot-density evidence.
- **Verify / review:** adversarial suppression/complementary/differencing
  fixtures across all endpoints; independent privacy/security/architecture review.

#### W3-00D — measurement methodology contract

- **Scope / authority:** define modelled potential contacts, measured-vs-
  modelled hierarchy, units, provenance/vintage, missing-data rules,
  uncertainty, correction/reissue and prohibited view/reach/attribution claims
  (§22.4/§27, RM16, Q12/Q30, D20). Define Campaign Performance Analysis as
  the standard deliverable. Define true ROI only when advertiser conversion
  and revenue inputs plus an approved reproducible ROI method are all present;
  otherwise the ROI section and claim are omitted.
- **Acceptance:** every visible metric/label maps to a definition and
  uncertainty treatment; the ROI gate fails closed; terminology audit finds no
  overclaim.
- **Verify / review:** golden performance-only and true-ROI methodology
  fixtures, missing-input/method cases and copy audit; independent measurement/
  legal/commercial review.

#### W3-00E — immutable measurement runs and proof manifests

- **Scope / authority:** immutable formula-versioned run plus proof manifest
  linking creative, approved installation evidence, assignment, period,
  inputs/provenance and correction lineage (§22/§27, RM16, D20). The frozen
  input manifest records whether the report is performance-only or ROI-enabled
  and the approved method revision when enabled.
- **Acceptance:** frozen input reproduces result; changed input creates new
  run/reissue; missing proof or ROI prerequisite fails closed without silently
  relabelling performance as ROI.
- **Verify / review:** migration/reproducibility/fingerprint/lineage and report
  integration tests; independent measurement/architecture/audit review.

#### W3-01A — typed retargeting source registry

- **Scope / authority:** advertiser manages five D11 planning-source types;
  admin monitors; metadata is typed/allowlisted with provenance, basis, expiry
  and DSR fields; identifiers/uploads/free text are rejected (§22.4, RM16,
  D11/Q11).
- **Acceptance:** all types and lifecycle work; organization isolation holds;
  identity-like/free-text input fails clearly.
- **Verify / review:** API/UI/validation/expiry/provenance and admin-advertiser
  e2e; independent privacy/security review.

#### W3-01B — source/campaign/zone linkage

- **Scope / authority:** owned planning sources link to campaigns, target zones
  and time windows without raw-ping access (§22.4, D11/Q11).
- **Acceptance:** ownership/date/zone compatibility is server-enforced;
  cross-org and raw-data joins reject; link history is auditable.
- **Verify / review:** authorization/compatibility/lifecycle and advertiser
  setup e2e; privacy/authorization review.

#### W3-01C — governed exposure segments

- **Scope / authority:** worker materializes versioned campaign coverage-cell/
  time-window aggregates from approved analytics and applies disclosure
  suppression; no export activation (§22.1–22.3, Q11).
- **Acceptance:** retries converge; provenance/fingerprint drift makes stale;
  below-threshold cells suppress; organizations isolate.
- **Verify / review:** frozen-time/worker/idempotency/provenance/suppression
  tests; independent privacy/measurement/concurrency review.

#### W3-01D — recommendations, export and gated activation

- **Scope / authority:** advertiser reports/dashboard and admin monitoring show
  contextual geography/time recommendations derived from governed segments,
  with provenance/disclaimer/uncertainty; the same approved aggregate supports
  controlled export and an auditable ad-platform activation adapter
  (§22.3/22.4, D11/D18/D20/Q11). The outbound schema allowlists only aggregate
  geography/cell, time-window and contextual campaign fields; identifiers,
  raw routes and person-level payloads reject. No identity resolution. Live
  push fails closed
  until `EXT-AD-PLATFORM` supplies accounts, legal approval, API access,
  credentials and budget.
- **Acceptance:** no driver/trip/precise timestamp or person identifier is
  exposed; rejected payloads never reach the adapter; suppressed/empty states
  and access boundaries are correct.
- **Verify / review:** API/UI/report/export, fake-adapter approval/idempotency
  and fail-closed gate e2e plus terminology audit; independent privacy/
  measurement/security/claims review.

#### W3-02A — exposure score v1

- **Scope / authority:** formula-versioned campaign/route exposure score with
  documented inputs, missing-data and uncertainty behavior beside—not inside—
  impression estimates (§22.4/§30).
- **Acceptance:** frozen formula is reproducible; history never rescores;
  UI distinguishes score, impressions and contacts.
- **Verify / review:** golden formula/version-freeze/reproducibility and UI
  tests; independent measurement/architecture review.

#### W3-02B — high-exposure zone insights

- **Scope / authority:** governed ranked campaign/city cells or zones appear
  in advertiser/admin dashboards, maps and report sections (§22.4, D11).
- **Acceptance:** ranking/ties/empty/suppressed cases reproduce from the
  measurement run and always pass disclosure control.
- **Verify / review:** ranking/access/map/report/browser e2e; independent
  privacy/measurement/maps review.

#### W3-03A — matching recommendations

- **Scope / authority:** deterministic eligibility/scoring ranks driver/vehicle
  candidates; admin explicitly chooses, never automatic assignment (§21,
  RM9, Q7/Q16/Q19).
- **Acceptance:** stale candidate is rechecked; city/type/current-load and
  exclusivity rules hold; lost race fails safely.
- **Verify / review:** scoring/eligibility/race/query and admin e2e; fairness/
  concurrency/operations review.

#### W3-03B — complete offer lifecycle

- **Scope / authority:** terms-complete expiring offer supports driver accept/
  decline; accepted terms are immutable dispute evidence; admin final
  assignment/activation remains (§21, Q7/Q8).
- **Acceptance:** rate/dates/area/branding display; accept/decline/expiry races
  converge; no activation without accepted frozen terms and W2 gates.
- **Verify / review:** state/race/API and driver-admin e2e; independent money/
  audit/concurrency review.

#### W3-03C — activity floor and inactivity handling

- **Scope / authority:** configurable verified-hours/week and seven-day
  inactivity sweep create operations flag/notification without silently
  terminating assignment or earnings (§21, Q20).
- **Acceptance:** exact boundaries, retry and missing-analytics behavior hold;
  resumed activity recovers as designed.
- **Verify / review:** frozen-time/idempotent-worker/admin UI/e2e; money/
  operations review.

#### W3-04A — public driver application

- **Scope / authority:** abuse-resistant public registration creates pending
  application/user/profile and visible status; invite/referral stays a gate
  (§23, D1/D8, Q13). No work access or KYC approval yet.
- **Acceptance:** duplicate/enumeration abuse resists; pending user cannot enter
  work flows; admin sees queue.
- **Verify / review:** rate-limit/duplicate/auth-state/public→admin e2e;
  independent auth/security/privacy review.

#### W3-04B — KYC/bank onboarding approval

- **Scope / authority:** public applicant reuses W2 secure document, encrypted
  driver-identity/licence/agreement and MNY-10A payee/account flows; admin
  approves only the complete person/payee stage (§19/§23, RM18, Q23/Q26/Q27).
  Vehicle registration/insurance/photos and work eligibility belong to W3-04C.
- **Acceptance:** missing/rejected/expired/unsafe item blocks; resubmission and
  audit work; this approval remains **non-work-eligible** until W3-04C approves
  an active vehicle. Legal wording gates go-live.
- **Verify / review:** complete application→KYC→approval e2e plus security/
  encryption/read-audit tests; independent threat/privacy/money review.

#### W3-04C — driver vehicle profile and approval

- **Scope / authority:** an identity/KYC-approved but non-work-eligible driver
  creates and maintains the proposal Module C vehicle profile (type, plate,
  registration, insurance and vehicle photos) through explicit
  pending-review/approved/rejected/expired revisions; admin owns approval.
  Reuse W2 stored-file/KYC controls and existing vehicle/assignment invariants.
- **Acceptance:** a driver cannot edit another vehicle or self-approve; a
  material change invalidates the prior approval/evidence without rewriting
  history; work eligibility is granted only when driver KYC/payee and at least
  one active vehicle are approved; only such a vehicle may receive/activate an
  assignment.
- **Verify / review:** ownership/RBAC/revision/expiry/exclusivity/API and
  driver→admin→approved-vehicle e2e; security/fraud/operations review.

### W4 production PWA, launch and handover

#### W4-01A — PWA foundation and session security

- **Scope / authority:** production manifest/service-worker/installability,
  BFF-cookie session renewal/logout/revocation, staged geolocation permission,
  fail-closed IndexedDB/Web Locks capability checks and redacted logs (§23,
  D18/RM17/RM18). Native credentials/push/store assets are Phase 2.
- **Acceptance:** install/reinstall, session expiry/revocation, permission
  denial/revocation, missing storage/lock and unsupported browser states behave
  safely on representative Android/iOS devices.
- **Verify / review:** BFF/auth, installability, storage/lock and real-device
  tests; independent PWA/security/privacy review.

#### W4-01B — screen-on tracking and durable sync

- **Scope / authority:** production explicit Start/End, mounted-phone screen-on
  enforcement, visibility/background degradation, durable queue, stable
  idempotency, offline/retry and `active/degraded/stopped` health using D15/D16
  (§23, D18/Q10).
- **Acceptance:** no acknowledged loss/duplicate under reload, airplane/offline,
  low-power, permission, storage/lock or visibility transitions; unsupported
  background capture is never claimed; completeness/latency/accuracy/battery
  SLOs pass.
- **Verify / review:** Android/iOS browser/device matrix and live synthetic
  API/worker/seal journey; independent PWA/architecture/security/data-loss review.

#### W4-01C — PWA onboarding and campaign journey

- **Scope / authority:** integrate the governed application/onboarding, vehicle
  profile, recommendations/offers, activation and explicit Start/End tracking
  into the installable PWA through the BFF (proposal Module C as superseded by
  D18). This leaf owns client integration only; W3-04C owns vehicle backend/
  review behavior.
- **Acceptance:** supported Android/iOS combinations complete onboarding→
  approved vehicle→offer→activation→tracking with correct permission,
  screen/visibility degraded states and role access; the client cannot bypass
  server approval or activation gates.
- **Verify / review:** device/browser journey e2e across approval and tracking
  failure states; PWA/UX/security/fraud review.

#### W4-01D — PWA earnings, disputes and release rehearsal

- **Scope / authority:** complete campaign/trip history, `payout_v3` earnings
  breakdown, hold reasons/disputes, in-app notification integration,
  installability/offline shell and pilot distribution rehearsal (§23,
  D18/Q10/Q34). Store signing/listing and native push are Phase 2.
- **Acceptance:** money/history agrees with canonical backend balances; no
  sensitive location/KYC data enters notification/cache/log payloads; supported
  devices install and complete history→hold→dispute→outcome after reload/offline
  recovery.
- **Verify / review:** device/browser e2e, cache/redaction/session and install
  rehearsal; independent PWA/UX/security/money review.

#### W4-02A — governed maps and report experience

- **Scope / authority:** existing admin/advertiser maps and reports consume
  measurement runs, disclosure controls, safe labels, high zones, exposure
  score and contextual follow-up; admin raw route remains purpose-scoped
  (§27, RM15/RM16, D20). The standard title is Campaign Performance Analysis;
  ROI appears only when the frozen run records all required inputs and an
  approved method revision.
- **Acceptance:** no raw advertiser bypass or attribution/view/ROI overclaim;
  missing ROI prerequisites omit ROI; correct suppression/empty/access states
  and acceptable map latency.
- **Verify / review:** browser, performance-only and true-ROI golden fixtures,
  permission/load/terminology tests;
  independent privacy/measurement/maps review.

#### W4-02B — bounded CSV/PDF issuance

- **Scope / authority:** worker-generated basic CSV/PDF from frozen measurement
  run with hash/version/access/suppression/reissue; segment export remains
  disabled until Q31 (§27/§30, D11/D20/Q11/Q12/Q27/Q30/Q31). Issuance uses the
  Campaign Performance Analysis title by default and reproduces the frozen ROI
  gate decision. Build/test is synthetic performance-only per the register:
  `EXT-REPORT-METHOD` gates first live issuance at the W4-03B pilot gate, not
  this item's build entry.
- **Acceptance:** file reproduces source run, cannot leak suppressed data,
  authorization holds, legal switch fails closed and ROI is absent unless both
  required data and approved method are present.
- **Verify / review:** performance-only/true-ROI golden files, missing-input/
  method, hash/tamper/RBAC/worker retry/load/browser download tests; independent
  privacy/measurement/security review.

#### W4-03A — client-owned release environment

- **Scope / authority:** approved client account/domain gets hardened release
  candidate with secrets, object storage, managed PostGIS verification, TLS,
  observability and rollback/recovery (§25/§26, RM17, Q29/Q32).
- **Acceptance:** config/secrets/edge exposure pass; migrations roll; encrypted
  off-host backup restores; release smoke/load/security checks pass.
- **Verify / review:** deployment, rollback, restore, exposure scan and full
  smoke; independent deployment/security/data-loss review.

#### W4-03B — pilot gate and acceptance suite

- **Scope / authority:** one launch checklist mechanically proves G-money,
  G-GPS, G-commercial, G-advertiser, G-moduleG and G-pilot; records the real
  company/commercial facts, evidence policy, the approved measurement/ROI
  methodology (`EXT-REPORT-METHOD` — the live-issuance gate W4-02B builds
  against synthetically), Q26/Q31 legal/privacy approval,
  automated-disbursement provider readiness, D19 permit evidence and D18/D20
  Cardvert/Abuja pilot facts, reporting rule and owners (§35.3).
- **Acceptance:** full advertiser→admin→PWA→GPS→measurement→retargeting/export
  or aggregate contextual gated activation→Campaign Performance Analysis
  (plus ROI only when its gate passes)→automated payout→incident/recovery
  simulation passes or
  reports an explicit blocker. The planned cohort is Abuja, 10 vehicles, five
  paying advertisers and three months; coverage target is at least 60% of the
  target area.
- **Verify / review:** whole-system acceptance suite and independent launch
  review spanning privacy, money, security, architecture and operations.

#### W4-04A — role-based onboarding and training

- **Scope / authority:** admin, advertiser and driver materials cover real
  release-candidate flows; operator rehearses privacy, KYC, fraud, payout,
  reporting and incident procedures (D11, proposal Month 5).
- **Acceptance:** fresh users complete role tasks; every link/command/
  escalation path works and acceptance is recorded.
- **Verify / review:** facilitated usability and operator rehearsal;
  operations/privacy/money review.

#### W4-03C — controlled pilot and stabilization

- **Scope / authority:** only after W4-03B and W4-04A, approved pilot users run
  the D18 three-month Abuja cohort with GPS/battery/queue/report/payout/support
  telemetry, incident and rollback criteria. Developer supports initial pilot
  operations while training Somto's team (Q30/Q31/Q33).
- **Acceptance:** sampled reports reproduce; payouts reconcile; problems do
  not silently change policies/formulas; acceptance/deferment register signed.
- **Verify / review:** burn-in, incident/support records, report replay,
  payout reconciliation and rollback drill; operations/privacy/money review.

#### W4-04B — handover, support and roadmap closure

- **Scope / authority:** system/deployment docs, RACI, credential handover,
  backup schedule, support SLAs/escalation, known risks/deferments and
  evidence-linked post-MVP roadmap (D11, proposal final outcome).
- **Acceptance:** named owners accept artifacts; restore/incident handover is
  rehearsed; proposal/architecture/decisions/progress/repository agree.
- **Verify / review:** documentation link/command audit, ownership sign-off
  and independent architecture/operations closure review.

## Coverage proof

| Source requirement | Complete owning path |
| --- | --- |
| RM1, RM3, RM4, RM5 | Already built; preserved and inherited by R14-B/W4-01B |
| RM2 | FND-02A/B |
| RM6 | MNY-06A/B/C |
| RM7 | FND-07 |
| RM8 | MNY-08A/B/C + MNY-03A |
| RM9 | MNY-09A + W2-03C/D/G + W3-03 + W4-01 |
| RM10 | MNY-10A/B/C |
| RM11 | MNY-11A |
| RM12 | W2-00A/C + W2-03D/E |
| RM13 | W2-00B + W2-01B/C/D + W2-03D/F |
| RM14 | Native requirement deferred to Phase 2 by D18; R14-A/B + W4-01A/B/C/D now own the replacement production-PWA proof |
| RM15 | W3-00A/B/C + W4-02A/B |
| RM16 | W3-00D/E + W3-01/02 + W4-02A/B |
| RM17 | R14-A/B + R17-A + W4-03A/B/C |
| RM18 | MNY-10A + W2-02A/B/D/E + W3-04B/C + W4-01/03 |
| Proposal A — admin | W1 money operations + W2 admin queues + W3 monitoring + W4 reports/training |
| Proposal B — advertiser | W2-00D company profile + W2 commercial/creative/campaign flows + W3 retargeting/analytics + W4 reports |
| Proposal B advertiser registration exclusion | Operator-led advertiser/org onboarding per D1; public advertiser self-serve is proposal §8 post-MVP |
| Proposal C — driver pilot client (D18 override) | W3-03/04A/B/C + W4-01A/B/C/D production PWA; native background client is Phase 2 |
| Proposal D — analytics/impressions | Built engine + W3-00D/E + W3-01C/D + W3-02 |
| Proposal E — driver payouts | Built payout v2 history + MNY-06 (`payout_v3`)/08/03/10/11 + W2 earning gates |
| Proposal F — heatmaps/reporting | W3-00C/D/E + W3-02B + W4-02A/B |
| Proposal G — retargeting | W3-01A/B/C/D + W3-02B + W4-02A/B |
| §30 advertiser/admin password reset | W2-04D |
| §30 WhatsApp opt-in / phone verification | W2-04D; W2-04C consumes only verified active consent |
| §30 driver vehicle-profile ownership | W3-04C backend/review + W4-01C PWA integration |
| Pilot and handover | R17-A + W4-03A/B/C + W4-04A/B |

## External prerequisite register

These stable IDs never disappear from the queue. `PRESENT` requires evidence;
`MISSING` blocks any checklist item that references the ID. Missing live-use
facts that are not build-entry prerequisites remain gates but do not block an
otherwise synthetic/provider-neutral checklist item or its package.

| ID | State | Input | Evidence | Needed by / exact effect |
| --- | --- | --- | --- | --- |
| **EXT-STAGING-APPROVAL** | MISSING | External staging provider/account/spend approval | — | Deferred external staging deployment/restore validation and later W4 release/pilot; D23 says it does not block R17-A's provider-neutral build proof |
| **EXT-RM2-POLICY** | PRESENT | Owner-approved RM2 stationary policy and parameters | `docs/decisions-log.md` D22; reviewed synthetic Option A | FND-02B implementation binds 120s/25m/2-confirm/1-release/per-trip values for new acceptances |
| **EXT-PAYMENT-PROVIDER** | MISSING | Payment provider/sandbox/signing secrets | — | Live W2-01C adapter and provider refunds |
| **EXT-STORAGE-PROVIDER** | MISSING | Production object-storage provider, account and region | — | W2-02A production adoption |
| **EXT-MALWARE-SCANNER** | MISSING | Malware scanner/provider | — | W2-02B fail-closed scan integration |
| **EXT-KMS-CUSTODY** | MISSING | KMS/vault and production key custodian | — | Production W2-02 controls; pilot interim is D17's typed-Settings-key envelope encryption through the shared crypto port |
| **EXT-EMAIL-PROVIDER** | MISSING | Email provider and verified sending identity | — | Live W2-04B delivery |
| **EXT-BUDGET-POLICY** | MISSING | Production budget alert/pause/resume values and approval | — | Live W2-01E policy adoption; configurable/provider-neutral implementation remains runnable |
| **EXT-PHONE-OPERATOR** | MISSING | Named phone-verification operator and approved manual WhatsApp/voice account | — | W2-04D pilot sends; generic challenge/consent tests remain synthetic |
| **EXT-BASEMAP** | MISSING | Production basemap provider/licence/account/API key | — | W4-02A live map release and W4-03B; public CARTO defaults remain development-only, while provider-neutral/local W4-02A build and tests remain runnable |
| **EXT-STORE-ASSETS** | MISSING | App Store and Play accounts/assets | — | Phase 2 native signing/listing only; not a PWA-pilot prerequisite |
| **EXT-RELEASE-ENV** | MISSING | Q32 client-owned account/domain, provider, budget and access action for Cardvert | — | W4-03A release environment; ownership direction and brand are confirmed, actual environment is absent |
| **EXT-PILOT-FACTS** | PRESENT | Abuja; 10 vehicles; 5 paying advertisers; 3 months; Campaign Performance Analysis, offline-to-online targeting and at least 60% target-area coverage; developer supports the initial pilot while training Somto operations | `docs/decisions-log.md` D18/D20, Q30/Q33 | W4-03B uses the confirmed cohort and performance-report goal; true ROI remains conditional on `EXT-REPORT-METHOD` inputs/method |
| **EXT-REPORT-METHOD** | MISSING | Client approval of impression-estimation methodology/labels and, for any true ROI output, the required conversion/revenue input schema plus reproducible attribution, cost-basis, time-window, exclusion and correction method | — | Performance-only contracts can build/test; first live issued report needs approved measurement method, and ROI remains omitted until its additional inputs/method are approved |
| **EXT-Q28-COMPANY** | MISSING | Terrax Media registered issuer name, TIN, address, invoice wording and accountant confirmation | — | VAT-inclusive display with itemised net/VAT/gross is confirmed; real W2-01A invoice issuance waits for these statutory facts |
| **EXT-COMMERCIAL-VALUES** | MISSING | Custom-quotation values/components, commissions, base/premium payout rates and production/vendor values | — | Real W2-00A/MNY-06 commercial use; schema remains configurable |
| **EXT-EVIDENCE-POLICY** | MISSING | Evidence uploader/views/renewal and RM9 challenge/spot-check thresholds | — | Pilot W2-03C/G enforcement |
| **EXT-LEGAL-PRIVACY** | MISSING | Q26/Q31 wording, privacy owner and retention/DSR decisions | — | KYC/live GPS/retargeting go-live |
| **EXT-DISBURSEMENT-PROVIDER** | MISSING | Approved automated bank-transfer provider, account, sandbox, signing/webhook credentials and production approval | — | Provider-neutral MNY-10B/C can build/test; financially effective submission and W4-03B cannot proceed |
| **EXT-AD-PLATFORM** | MISSING | Named ad-platform accounts, legal approval, API access/credentials and activation budget for aggregate geography/time/context activation | — | W3-01D can build/test provider-neutrally; any live aggregate contextual push remains disabled; person-level activation is outside the pilot |
| **EXT-PILOT-PERMITS** | MISSING | Abuja permit/authority evidence for the selected vehicles/campaigns | — | D19 assigns Terrax ownership and vendor coordination; W4-03B/launch remains blocked until evidence is approved |
| **EXT-PKG07-OWNER-RELEASE** | PRESENT | Explicit project-owner release to start Package 7 after this bounded Package 6 controller assignment | Project owner’s 25 Aug 2026 standing instruction to advance the next dependency-safe package automatically | W4-01A build admission is authorized; this is not a product or live-use prerequisite |
| **EXT-RM2-CALIBRATION-DATA** | MISSING | P1 parked-jitter and P2 Abuja-congestion field corpora (devices, participants, locations) per the owner-authorized 19 Aug 2026 Option-A collection program | — | Optional post-build calibration for a later effective revision; D22's reviewed synthetic selection is build-authoritative and this input blocks no checklist item |
| **EXT-BRAND-APPROVAL** | MISSING | Final Cardvert logo/brand asset pack and named client approver | — | Client-facing release assets and final handover acceptance; neutral development assets remain usable for build/test |
| **EXT-CAMPAIGN-BUDGET-SCOPE** | MISSING | Client decision on whether printing and other fixed costs consume the governed campaign budget | — | Production commercial configuration and acceptance; configurable synthetic budget enforcement remains runnable |
| **EXT-SETTLEMENT-BANK** | MISSING | Approved settlement bank-account details and custody/verification evidence | — | Live financial settlement only; no value is stored or invented before approved secure intake |
| **EXT-UPLOAD-POLICY** | MISSING | Client-approved file types and maximum sizes for each evidence/upload surface | — | Live upload policy adoption; existing fail-closed configurable limits remain build/test authority |
| **EXT-MESSAGE-COPY** | MISSING | Approved sender name and production email/WhatsApp/voice message copy | — | Live outbound communications; provider-neutral templates and delivery controls remain runnable |
| **EXT-RM2-APPROVER** | MISSING | Named client approver for any future RM2 calibration revision | — | Optional post-build RM2 revision only; D22 remains authoritative for current build and pilot preparation |
| **EXT-OPERATIONS-OWNER** | MISSING | Named receiving operations owner for Q33 training, pilot operations and handover | — | W4-04A/B rehearsal acceptance and operational handover; documentation/preparation remains runnable |

### Deferred post-build validation register

D23 keeps the following evidence visibly incomplete. These rows are not claims
that physical or external validation ran; they preserve the later gate and the
owner/action needed to run it.

| Validation | State | Deferred evidence | Required before |
| --- | --- | --- | --- |
| **DV-PWA-PHYSICAL-MATRIX** | NOT RUN — DEVICE ACCESS REQUIRED | Representative Android/iPhone installability, grant/denial/revocation, reload/offline/visibility/storage/lock behavior and completeness/sync-latency measurements | W4 production-PWA pilot acceptance / any real driver GPS |
| **DV-PWA-ROUTE-BATTERY** | NOT RUN — DEVICE/ROUTE ACCESS REQUIRED | Controlled real-route accuracy and four-hour battery measurement on the supported physical matrix | W4 production-PWA pilot acceptance |
| **DV-STAGING-LIVE** | NOT RUN — EXT-STAGING-APPROVAL | Deploy provider-neutral topology to an approved external environment; capture public-edge smoke, worker recovery, exact backup marker/revision restore and rollback evidence | W4 client-owned release and pilot gates |

Post-pilot work remains explicitly deferred: the native background driver app
and store distribution, expanded recurring billing, edge-AI vehicle/pedestrian
counting and multi-city optimisation (architecture §31). Automated driver
transfers are pilot scope. Aggregate geography/time/context ad-platform
activation is D18/D20 scope but stays fail-closed until `EXT-AD-PLATFORM` is
present; person-level activation is outside the pilot.

## Canonical repository

`/Users/oluwasolaonigbinde/Projects/mobility-pkg01` on `feat/pkg-01`. The former
`mobility-master` directory was an obsolete Slice-0-only copy — never use it
to determine delivery status. When documentation conflicts, committed source
and Git history win.

## Delivered so far

| Stream | Status | Evidence |
| --- | --- | --- |
| Backend slices 0–13 (closed loop) | Complete | `docs/build-loop/slice-log.md`; closure commit `0dfb284` |
| Frontend F0–F6 (advertiser/driver/admin surfaces) | Complete as built demo/synthetic surfaces; the later RM4/RM5 PWA defects were closed by W0-F (D15/D16). Live authorization remains governed below. | Git `9189fe4`…`a5bcbb6`; `docs/archive/fablev1-work.md` journal |
| F7 auth/session hardening + audit + CI + backups | Complete, merged | Git `f40e0c4`…`236c2e4` (PR #1); architecture changelog v1.4 |
| Automated post-trip pipeline (arq worker) | Complete, merged | Git `159b0b1`, `4f69ef6`; architecture v1.5–v1.6 |
| S1 — payout engine v2 (hourly pay + daily caps, D2/D4/D9) | Complete, merged — RM1 fixed and the original whole-trip stationary grace retained for immutable payout-v2 history | Git `f9cd8ca`; architecture v1.8/v1.15, §16.1 [BUILT] |
| PKG-01 — foundations and empirical risk proof | Complete — RM2/RM6/RM7 closed; payout-v3 frozen parked-time behavior, PWA protocol/interrupted-flow build proof and provider-neutral release/recovery proof delivered; physical/live validation remains explicitly deferred | Git `d2cd424`…`be726a2` plus the package closure commit; architecture v1.30; D22/D23; automated/PostGIS/frontend/browser/recovery evidence |
| PKG-02 — money integrity and payout operations | Complete — RM8/RM10/RM11 closed; copied-route control, authoritative holds, clean release, encrypted payees, frozen provider instructions, line finality and carry-forward debt delivered provider-neutrally | Git through `e3a505e`; migrations `0022`–`0031`; architecture v1.37; Postgres/frontend/contract/synthetic end-to-end evidence and consolidated review resolved |
| PKG-06 / W3-03A–W3-04A — matching, offers, activity and public application | Complete checkpoints — advisory cars-only ranking, immutable expiring offers, reviewable activity flags and default-off non-enumerating pending driver applications; W3-04B/C are dependency-blocked | Package 6 commits through the W3-04A blocked-frontier checkpoint with selectively adopted Package 5 audit corrections; architecture v1.48–v1.52; focused PostgreSQL/Redis/backend/frontend/contract/live-journey evidence and consolidated reviews resolved |
| S4 — data lifecycle (ping partitions, retention purge, audit backfill, D10) | Complete, merged | Git `a879a3d`…`4f487e7`; architecture v1.9, §24.2 [BUILT] |
| W0-F — trip finality protocol + durable client queue (RM3/RM4/RM5, D15) | Complete — sealed-only money chain, post-seal quarantine, IndexedDB queue with stable retry keys; independently reviewed and hardened (D16: apply-after-initial-payout, pre-seal analytics recompute, fail-closed client) | Migrations `0016`+`0017`; architecture v1.16/v1.17; `tests/test_trip_seal.py`; live compose e2e |
| Pre-production ops (production Compose overlay, release smoke, backup/restore rehearsal) | Complete locally, **not deployed** | Git from `006d94e`; `docker-compose.production.yml`, `docs/runbook.md` |
| Current API contract | 31 migrations; controlled public baseline integration completed at PKG-02 closure | Payee/account, payout-batch, line-reconciliation, paid-balance and debt APIs are synchronized with the existing fraud/dispute/release contract across `docs/api/openapi.snapshot.json`, `openapi.json` and `schema.d.ts`. Later public endpoint/schema work must move all three artifacts together. |

**Nothing is deployed.** Staging/production remain research-only
(`docs/staging-options.md`) pending provider, budget, and operator approval
(Q32).

### Built does not mean live-authorized

Several useful interfaces predate the independent-review gates and may be used
only with demo/synthetic data until their owning checklist items land:

- Existing advertiser heatmaps/reports are **not live-authorized** under
  G-advertiser. W3-00D has supplied the safe build-time labels and methodology
  contract; W3-00C/E and W4-02A/B must still add disclosure control,
  reproducible measurement runs and governed issuance.
- PWA trip tracking and its durable queue are a tested protocol baseline, but
  **real-driver tracking is blocked** by G-GPS until RM2/RM9/RM15/RM18 close;
  W4-01 turns this surface into the D18 production screen-on pilot client.
- Payout rules, fraud review, release, encrypted payees, batch and reconciliation
  screens are provider-neutral synthetic foundations. The software G-money
  defects are closed, but **no real transfer is authorized** until
  `EXT-DISBURSEMENT-PROVIDER` supplies the approved provider and credentials.
- Current advertiser scheduling and driver activation flows are foundations,
  not the target commercial authority: G-commercial and W2-03A/D replace
  direct self-scheduling/activation before any live campaign.

## Where we are in the roadmap (architecture §31)

- **W0 — review remediation (new, 6 Aug 2026, D13):** **complete for PKG-01's
  built-code defects** — RM1
  fixed and RM2's renewable-grace half fixed 6 Aug 2026 (migration `0015`);
  **RM3/RM4/RM5 (trip seal protocol, stable retry keys, durable client queue)
  fixed 9 Aug 2026** (migration `0016`, D15, 465 tests green on PostGIS). It
  leads the remaining work. An independent code-verified review originally
  found seven defects in already-built code (architecture §35.1) plus eleven
  specification rows for unbuilt domains. RM1/RM3/RM4/RM5 are now closed,
  RM7 closed 16 Aug 2026 (PKG-01 FND-07, architecture v1.25); RM6 closed with
  payout-v3 revision/binding/correction authority, and RM2 closed under D22's
  acceptance-frozen rolling-displacement rule (architecture v1.30). Later
  tuning from real-route data creates a new revision and never rewrites history.
- **W1 — money correctness:** complete provider-neutrally. Worker, immutable
  payout history/corrections, data lifecycle, current fraud assessment and
  copied-route control, one hold predicate, clean/SLA release, encrypted payee
  versions, reconciled payout batches and carry-forward debt are built. Live
  transfer remains gated only by `EXT-DISBURSEMENT-PROVIDER`.
- **W2 — commercial layer:** not started. Billing/invoices (§15; W2-01A),
  file storage (§19), campaign/creative approval + installation evidence
  (§18), notification channels (§20).
- **W3 — reach:** not started. Retargeting at full Module G scope (§22),
  matching recommender + activity sweeps (§21), driver self-registration
  (§23).
- **W4 — production PWA + pilot readiness (D18):** not started. Installable
  screen-on PWA hardening/device proof, remaining CSV/PDF exports, Cardvert
  client-owned deployment, Abuja pilot and onboarding/training materials.

## Promise vs. delivery, by proposal module

| Proposal module | Built/demo-capable today (not necessarily live-authorized) | Outstanding / live-enablement owner |
| --- | --- | --- |
| A. Admin platform | Login/RBAC, user+org onboarding, drivers/vehicles, assignments, fraud review/disputes, payout rules/corrections, release SLA, payees, payout batches/reconciliation, traffic profiles and audit UI | Campaign/creative approval queues (W2), installation evidence (W2), retargeting monitoring (W3), exports (W4); live transfer provider input remains external |
| B. Advertiser dashboard | Campaigns CRUD, zones editor, analytics, demo heatmaps/reports/charts and payout-derived cost summaries | Company profile (W2-00D), creative *upload* (W2 — metadata-only today), billing/invoices (W2), governed approval/activation (W2), retargeting setup + insights, exposure score + high-exposure zone views (W3), disclosure-safe reports + CSV/PDF export (W4) |
| C. Driver app | Installable PWA: jobs, synthetic/demo trip tracking (idempotent ping batches), earnings + S1 trip breakdown, basic profile, durable offline ping queue + trip seal protocol (D15) | Offer accept/decline, self-registration, KYC and driver-owned vehicle lifecycle (W3); verified contact/notifications (W2); **production screen-on PWA/device proof** (W4). Native background app is Phase 2 |
| D. Analytics & impression engine | Route analytics, fraud flags, impression estimates, exposure/heatmap aggregation, payout eligibility classifier | Exposure score metric (`exposure_v1`) + high-exposure zone identification + retargeting insight capture (W3) |
| E. Dynamic driver payouts | Payout-v2/v3 immutable history, acceptance-frozen terms, maker-checker corrections, authoritative fraud holds, clean/SLA release, encrypted payees, frozen batches, line-level paid finality and carry-forward debt | Financially effective automated transfer remains disabled until `EXT-DISBURSEMENT-PROVIDER`; later KYC/provider approval lives in its owning packages |
| F. Heatmaps & reporting | Demo heatmap/route/report screens and daily metrics | Central disclosure/methodology/runs (W3), high-exposure zone + follow-up-targeting sections (W3), governed UI + CSV/PDF (W4); G-advertiser controls live use |
| G. Online-to-offline retargeting | — (privacy boundary designed, §22) | Entire module (W3): sources, segments, linkage, insights, controlled export and gated aggregate geography/time/context activation; identifiers/person-level payloads reject and live actions require legal/`EXT-AD-PLATFORM` inputs |

## Documentation authority

| Question | Source of truth |
| --- | --- |
| What the MVP must deliver | Direct client answers and approvals in `docs/decisions-log.md` D18–D20 override conflicting D11 proposal/default wording; the proposal remains scope context |
| How it is designed (current + target) | `docs/architecture.md` |
| Product decisions + Q1–Q34 statuses | `docs/decisions-log.md` (Part 1 history, Part 2 statuses) |
| What is authorised next and in what order | this file's package execution lock; checklist dependencies control internal checkpoints |
| What has been delivered so far | this file (control summary) → architecture changelog + Git/test evidence for detail |
| How to operate it | `docs/runbook.md` |
| Historical evidence | `docs/build-loop/` (closed backend ledger), `docs/archive/` |

## Update rules

1. A landed package updates this file in the same change: checklist evidence,
   package `DONE` status, ordered promotion/BLOCKED markings, both top control
   pointer/controller state, delivered-so-far row, wave position, and the
   module table. Exactly one package is active unless explicitly paused.
2. Client answers land in `decisions-log.md` first; if they change scope or
   design, `architecture.md` amends in the same commit — this file only
   records resulting *delivered* changes.
3. A future idea or owner request enters the relevant package/checklist before code is
   written. Only the project owner may intentionally reorder it; record why.
4. A package `DONE` claim requires every owned checklist item `DONE`, plus
   implementation, deterministic verification, a live
   simulation proportional to risk, required independent review, docs, and
   concrete evidence. Code alone is not completion.
5. `docs/next-steps.md` and `docs/build-loop/` may inform a plan but never
   authorise a package or override current architecture §35.
