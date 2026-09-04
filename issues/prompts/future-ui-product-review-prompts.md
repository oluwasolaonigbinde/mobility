# Paused Cardvert UI and product-review prompt suite

Status: **PAUSED — do not run during first-pass audit reconciliation.**

These eleven prompts are preserved from the 1 September 2026 planning
conversation. Each prompt remains in its own fenced block for individual
copy/paste. Prompt 2 is the later, stronger UI-ergonomics revision. Prompt 8 may
be folded into Prompt 7 to conserve model usage, but its standalone wording is
retained for provenance.

Recommended model priority:

- Reserve GPT-5.6 Pro for Prompts 1, 7 and 11.
- Use GPT-5.6 Pro for Prompt 9 only if usage remains; otherwise use Claude Opus.
- Use Claude Opus for Prompts 2–6 and 10.
- Run Prompts 1–8 independently, then 9–11 sequentially with prior outputs.

### 1. End-to-end system-flow audit — GPT-5.6 Pro

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

You are the independent product-systems auditor for Cardvert, operated by Terrax Media.

SOURCE ACCESS:
- Use only the repository files, screenshots, route exports, and documents attached to this project/session.
- Local snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58.
- This SHA is for traceability only. Do not search GitHub, require a remote checkout, or stop merely because the private repository is inaccessible.
- If essential material is absent, identify the exact missing files or screenshots instead of inventing behavior.

TASK:
Audit how Cardvert works as one interconnected system. Reconstruct the real workflow from source evidence, not from route names or optimistic documentation.

Trace the lifecycle across:
- account and role onboarding
- advertiser and campaign creation
- planning and target-area selection
- quotation, funding, and payment states
- creative submission and approval
- driver/vehicle eligibility
- campaign matching and offers
- installation and proof
- activation
- route/exposure tracking, including offline-to-online handling
- analytics and campaign reporting
- earnings, reconciliation, and payout
- incidents, disputes, recovery, and audit
- operational handover and pilot gates

For every transition, identify:
1. initiating role
2. originating screen/module
3. backend action or persisted state
4. next expected state
5. screen where the result becomes visible
6. permission boundary
7. failure, empty, blocked, and retry behavior
8. whether the transition is fully connected, partially connected, misleading, or missing

OUTPUT:
- Executive verdict
- Evidence-linked system lifecycle
- Role-by-role journey map
- Module dependency map
- Broken or ambiguous transitions
- Orphaned screens/actions
- Contradictions between UI, API, state model, and documentation
- Priority-ranked remediation list
- Mermaid flowchart showing the actual system
- “No evidence found” wherever behavior cannot be established

Remain read-only. Do not edit files or assume external approvals have occurred.
```

### 2. UI ergonomics and information architecture — Claude Opus

This revised prompt supersedes the earlier information-architecture-only version.

```text
MODEL: Claude Opus, highest available reasoning.

You are the independent UX, interaction-design, and information-architecture auditor for Cardvert, operated by Terrax Media.

SOURCE ACCESS:
- Use only the repository files, screenshots, route exports, and documents attached to this project.
- Local snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58.
- This SHA is only a traceability label.
- Do not search GitHub, require a remote checkout, or stop because the private repository is inaccessible.
- If evidence is missing, identify the exact files, routes, states, or screenshots required.

OBJECTIVE:
Find the small, repeated UI decisions that individually appear harmless but collectively make Cardvert feel noisy, mechanical, inefficient, inconsistent, or AI-generated.

Do not limit the review to visual styling. Evaluate whether each interface presents the right information and actions in the cleanest form for the user’s real task.

REVIEW:

1. Tables and lists
- unnecessary or duplicated columns
- columns containing the same value or action in every row
- dedicated action columns that provide only one infrequent or destructive action
- information that belongs in a detail view, tooltip, summary, or secondary menu
- excessive status text
- poor column ordering
- missing row navigation
- missing sorting, filtering, search, pagination, or bulk operations
- actions that should operate on selected rows
- tables used where cards, summaries, queues, or grouped lists would communicate better
- desktop layouts that collapse poorly on smaller screens

Example heuristic:
If every active driver row has an “Action” column containing only “Suspend,” determine whether that action should instead appear in:
- a row overflow menu
- the driver detail page
- a controlled status menu
- a bulk-action toolbar
- or another contextually appropriate location

Do not blindly enforce this example. Evaluate action frequency, consequence, discoverability, accessibility, confirmation requirements, and future extensibility.

2. Action hierarchy
- too many equally prominent buttons
- destructive actions presented as primary actions
- secondary or rare actions consuming permanent space
- repeated actions that create visual noise
- actions shown before prerequisites are satisfied
- unclear button labels
- actions whose consequences are not explained
- missing confirmation or undo behavior
- controls that should be conditionally revealed
- menus containing only one pointless option
- actions available in inconsistent locations

3. Page composition
- weak or missing visual hierarchy
- excessive cards, borders, headings, badges, or explanatory panels
- repeated information
- empty space caused by inappropriate components
- important decisions buried below operational metadata
- internal identifiers shown more prominently than human-readable information
- dashboards that report data without helping the user decide what to do next
- pages that feel like database administration screens rather than product workflows

4. Forms
- unnecessary fields
- poor grouping
- fields shown before they become relevant
- unclear required/optional distinctions
- technical labels
- premature validation
- missing defaults
- inappropriate control types
- missing summaries before consequential submission
- forms that could be safely shortened through progressive disclosure

5. Status and feedback
- excessive status chips
- multiple labels communicating the same state
- status without explanation or next action
- implementation states exposed directly to users
- success messages that provide no useful confirmation
- expected blocked states rendered as errors
- loading states that obscure what is happening
- empty states without a useful next step

6. Navigation and information architecture
- modules organized around backend boundaries rather than user tasks
- duplicated destinations
- ambiguous menu labels
- unnecessary navigation depth
- hidden dependencies between pages
- missing breadcrumbs or return paths
- detail pages that fail to preserve list context
- workflows requiring users to remember information from another module
- role-inappropriate navigation

7. Consistency and design-system usage
- the same concept represented differently across modules
- inconsistent table, modal, drawer, filter, button, form, and status patterns
- one-off components without a justified interaction need
- inconsistent terminology
- inconsistent placement of primary, secondary, and destructive actions

8. Accessibility and safety
- hover-only actions
- icon-only actions without accessible names
- weak focus behavior
- insufficient keyboard interaction
- destructive actions placed too close to common actions
- reliance on color alone
- unclear disabled states
- confirmations that do not identify the affected record

FOR EVERY FINDING, PROVIDE:
- route or screen
- component/file evidence
- current behavior
- affected role
- why it creates friction or noise
- severity: critical, high, medium, or low
- recommended interaction
- alternatives considered
- reason for choosing the recommendation
- behavior that must remain unchanged
- responsive and accessibility implications
- acceptance criteria

IMPORTANT:
- Do not recommend changes solely because they are fashionable.
- Do not turn every row action into an overflow menu automatically.
- Preserve visible high-frequency actions when discoverability and speed justify them.
- Avoid hiding important actions so deeply that users cannot find them.
- Prefer simplification, consistency, and established components over redesign.
- Distinguish objective usability problems from subjective aesthetic preferences.
- Label uncertain recommendations as “requires usability validation.”
- Do not edit files.

OUTPUT:
1. Executive UX verdict
2. Highest-impact systemic patterns
3. Screen-by-screen findings
4. Table and list findings
5. Action-hierarchy findings
6. Navigation and information-architecture findings
7. Reusable design-system corrections
8. Quick wins
9. Structural improvements
10. Findings that require user testing rather than immediate implementation
11. Priority-ranked remediation backlog
12. “No owner decision required,” unless a genuine product decision exists
```

### 3. Human-facing language and “AI residue” audit — Claude Opus

```text
MODEL: Claude Opus, highest available reasoning.

Act as a senior product-content designer and ruthless human-language editor for Cardvert.

SOURCE ACCESS:
Use the attached Cardvert source files, screenshots, and documents. Snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58. Do not require remote repository access.

TASK:
Find text that sounds as though it was written for an AI, developer, auditor, database, or internal delivery process rather than a human user.

Inspect:
- navigation
- headings
- descriptions
- buttons
- forms and helper text
- validation
- empty states
- loading states
- error screens
- blocked/gated states
- notifications and emails
- dashboards
- tables and filters
- generated reports
- accessibility labels where visible
- internal status names exposed to users

Flag:
- implementation language
- internal identifiers, digests, UUIDs, registry codes, or checklist references
- unexplained compliance terminology
- robotic or verbose copy
- fake precision
- passive voice
- developer instructions
- AI-style meta commentary
- inconsistent Cardvert/Terrax Media terminology
- misleading promises about live data or approvals
- generic errors that conceal an expected business state

For every finding, return:
- exact current copy
- route/component/file
- intended audience
- why it is unsuitable
- replacement copy
- tone rationale
- whether legal/compliance confirmation is needed

Create a concise Cardvert voice guide covering:
- brand voice
- sentence style
- terminology
- button conventions
- empty/error/blocked-state patterns
- prohibited language
- distinction between Cardvert and Terrax Media

Do not rewrite legal policy or fabricate approvals. Remain read-only.
```

### 4. Admin and operations workflow audit — GPT-5.6 Pro

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

You are reviewing Cardvert specifically as an operations platform.

SOURCE ACCESS:
Use attached project files and screenshots. Local snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58. Do not attempt GitHub access or treat the SHA as a mandatory remote gate.

TASK:
Walk through the real daily work of an operations administrator from beginning to end.

Cover:
- account and role administration
- advertiser onboarding
- campaign review
- planning-source governance
- creative approval
- driver and vehicle eligibility
- campaign matching
- offers
- installation scheduling and evidence
- activation
- tracking and monitoring
- incidents and exceptions
- reporting
- financial reconciliation and payout readiness
- audit/history
- handover and pilot preparation

Evaluate:
- whether every action has a visible result
- whether the result appears in the expected downstream module
- whether staff can understand the next action
- whether status names are consistent
- whether filters and queues support actual work
- whether exception paths can be resolved
- whether expected external gates look like system failures
- whether sensitive actions have sufficient confirmation and auditability

OUTPUT:
- Admin “day in the life” journey
- Task-to-screen matrix
- Cross-module handoff defects
- Missing states/actions
- Confusing wording
- Operational risks
- Prioritized remediation backlog
- Mermaid operations workflow

Remain read-only.
```

### 5. Advertiser journey audit — Claude Opus

```text
MODEL: Claude Opus, highest available reasoning.

You are reviewing Cardvert from an advertiser/client perspective.

SOURCE ACCESS:
Use attached project files and screenshots. Snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58. Do not attempt remote Git verification.

TASK:
Evaluate whether a new advertiser can understand and confidently complete the full Cardvert journey without verbal coaching.

Trace:
- registration and organization setup
- campaign creation
- objectives and target-area planning
- quotation and budget
- funding/payment status
- creative requirements and submission
- approval and rejection
- launch readiness
- campaign activation
- progress and exposure reporting
- invoice/payment records
- support, incidents, and disputes
- campaign completion

Look for:
- unclear expectations
- missing prerequisites
- unexplained industry language
- misleading calls to action
- weak confirmation
- dead ends
- inconsistent statuses
- internal implementation text
- screens that require Terrax Media staff knowledge
- places where users cannot distinguish draft, submitted, approved, funded, active, paused, completed, or blocked

OUTPUT:
1. Advertiser journey map
2. Screen-by-screen comprehension findings
3. Missing or misleading states
4. Recommended wording
5. Recommended flow changes
6. Trust and transparency risks
7. Prioritized fixes
8. Mermaid advertiser journey

Remain read-only and do not invent commercial or legal policy.
```

### 6. Driver journey audit — Claude Opus

```text
MODEL: Claude Opus, highest available reasoning.

You are reviewing Cardvert from a driver’s perspective.

SOURCE ACCESS:
Use the attached project files and screenshots. Snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58. Do not require external repository access.

TASK:
Determine whether a driver can understand and complete the entire journey without operational staff explaining the software.

Trace:
- registration
- identity and eligibility
- vehicle registration
- document submission and review
- campaign discovery or matching
- offer acceptance
- installation scheduling
- installation proof
- activation
- route/trip tracking
- offline behavior and later synchronization
- campaign progress
- earnings
- payout readiness
- incidents, disputes, and support
- campaign completion and removal

Review the UI for:
- unclear requirements
- unsafe or distracting interactions
- misleading tracking claims
- hidden location/privacy implications
- poor offline explanations
- contradictory statuses
- missing feedback after submission
- internal codes or AI-facing text
- inaccessible recovery paths
- unclear earnings or payout conditions

OUTPUT:
- Driver journey map
- State and transition defects
- Copy replacements
- Offline/online experience findings
- Safety and trust concerns
- Priority-ranked remediation
- Mermaid driver journey

Remain read-only. Do not claim real tracking, payment, identity verification, or approval exists without evidence.
```

### 7. Errors, gates, and state-transition audit — GPT-5.6 Pro

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

You are auditing Cardvert’s user-visible state and error handling across frontend and backend.

SOURCE ACCESS:
Use attached repository files, API contracts, tests, and screenshots. Snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58. Do not attempt remote Git access.

KNOWN EXAMPLE:
The admin planning-sources page can receive HTTP 503 with PRIVACY_LIVE_USE_BLOCKED and render the generic “Something broke” screen. Treat this only as a starting example; independently inspect the wider system.

TASK:
Inventory the important backend outcomes and determine how each is presented in the UI.

Distinguish:
- genuine unexpected technical failure
- authentication failure
- permission denial
- incomplete setup
- validation failure
- expected external dependency
- privacy/legal approval gate
- payment/funding gate
- data-not-yet-available
- empty but valid result
- transient retryable failure
- permanent business rejection
- stale or conflicting state

For every important outcome, report:
- API/service source
- code/status
- affected routes
- current UI behavior
- correct human-facing state
- recommended title, explanation, action, and support path
- telemetry/audit requirement
- regression test needed

OUTPUT:
1. State-handling matrix
2. Incorrectly collapsed states
3. Expected gates currently shown as crashes
4. Internal details exposed to users
5. Recommended reusable frontend state components
6. Priority-ranked implementation slices
7. Acceptance criteria

Do not weaken or bypass legitimate gates. Remain read-only.
```

### 8. Client-owned approvals versus system-owned UX — GPT-5.6 Pro

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

You are defining the responsibility boundary between Cardvert, Terrax Media, and the client’s legal/privacy decision-makers.

SOURCE ACCESS:
Use attached Cardvert documentation, source, screenshots, and approval registries. Snapshot label: master at 38094d605830ccce111bcb0773ec1a249fed2d58. Do not attempt GitHub access.

TASK:
Separate:
A. information, decisions, documents, approvals, and real-world evidence that must come from the client or authorized external owner
B. behavior, wording, validation, guidance, and safe blocked states that the Cardvert product must provide

Pay special attention to:
- privacy and location processing
- retention
- data minimization
- consent and lawful basis
- sub-processors/providers
- payment and payout readiness
- driver/vehicle verification
- creative approval
- permits and deployment
- controlled pilot evidence
- audit and incident handling

The system must not draft approvals on the client’s behalf, but it also must not dump raw internal gate names or technical errors on users.

OUTPUT:
- Responsibility matrix
- Exact client-supplied inputs
- Exact system responsibilities
- Recommended human-facing wording while approval is absent
- What must be hidden from ordinary users
- What administrators need to see
- Safe next actions
- Approval-state lifecycle
- Genuine owner decisions

Remain read-only and do not provide legal conclusions.
```

### 9. Client-facing PRD and visual system guide — GPT-5.6 Pro

Run this after prompts 1–8 and attach their outputs.

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

You are the lead product analyst producing the client-facing Product Requirements and System Guide for Cardvert, operated by Terrax Media.

INPUTS:
- Attached Cardvert project sources and screenshots
- Outputs from the system, navigation, copy, role-journey, error-state, and responsibility audits
- Snapshot label: local master at 38094d605830ccce111bcb0773ec1a249fed2d58

SOURCE RULE:
Do not attempt GitHub access. Reconcile claims against the supplied evidence. Mark uncertainty explicitly.

AUDIENCE:
- client leadership
- marketing/campaign teams
- Terrax Media operations
- finance and compliance stakeholders
- future onboarding and support staff

Create a polished PRD/system guide that explains:
1. what Cardvert is
2. who uses it
3. business goals and non-goals
4. roles and permissions
5. every major module
6. the end-to-end campaign lifecycle
7. advertiser journey
8. driver journey
9. operations journey
10. how modules exchange state
11. important statuses and their meaning
12. offline-to-online behavior
13. reporting, earnings, reconciliation, and payout concepts
14. privacy, approval, and live-operation gates
15. what the client must provide
16. what Terrax Media operates
17. what users see when something is pending, blocked, rejected, or unavailable
18. launch-readiness boundaries
19. support and escalation model
20. glossary

VISUALS:
Include Mermaid diagrams for:
- overall system context
- campaign lifecycle
- advertiser journey
- driver journey
- admin/operations journey
- module dependency map
- approval and blocked-state lifecycle
- data flow at a non-sensitive conceptual level

WRITING STANDARD:
Use client-ready language, not engineering or AI language. Do not expose internal checklist IDs, hashes, registries, or implementation details unless placed in a clearly marked technical appendix.

Separate:
- confirmed implemented behavior
- configured but externally gated behavior
- proposed improvement
- unknown or missing evidence

Deliver a document that can be handed to the client with minimal editing.
```

### 10. Adversarial review of the PRD — Claude Opus

```text
MODEL: Claude Opus, highest available reasoning.

You are the independent editorial and product-logic reviewer of the attached Cardvert client-facing PRD/system guide.

Also use the attached audit outputs, screenshots, and source evidence where available. Do not attempt external repository access.

TASK:
Challenge whether the PRD truthfully and understandably explains the real system.

Find:
- claims unsupported by evidence
- missing modules or transitions
- contradictions
- terminology drift
- AI-generated or engineering-facing prose
- excessive jargon
- vague promises
- hidden external dependencies
- confused role responsibilities
- flow diagrams that do not match the text
- insufficient explanation of blocked, pending, rejected, offline, and error states
- language that could mislead a client about deployment, live payments, tracking, approvals, or pilot readiness

For each finding provide:
- section
- quoted or summarized problem
- evidence
- severity
- exact replacement or structural correction

Then produce:
1. Verdict: CLIENT-READY, NEEDS REVISION, or UNSAFE TO SHARE
2. Required corrections
3. Optional improvements
4. Missing evidence
5. Revised executive summary
6. Revised glossary
7. Diagram corrections
8. Final client-comprehension checklist

Remain read-only.
```

### 11. Consolidated implementation backlog — GPT-5.6 Pro

Run last, attaching all audit outputs and the reviewed PRD.

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

You are converting the completed Cardvert UX, workflow, copy, state-handling, and PRD audits into a bounded implementation programme.

INPUTS:
- All prior audit outputs
- Reviewed client-facing PRD
- Attached current source snapshot and screenshots
- Snapshot label: local master at 38094d605830ccce111bcb0773ec1a249fed2d58

Do not attempt GitHub access. Do not edit files.

TASK:
Reconcile duplicate, conflicting, speculative, and unsupported findings. Produce the smallest coherent implementation backlog that improves the real product without redesigning it unnecessarily.

Group work into:
- critical broken flows
- expected gates incorrectly rendered as failures
- misleading or AI-facing copy
- information architecture/navigation
- advertiser workflow
- driver workflow
- operations workflow
- cross-module state consistency
- accessibility and recovery
- client documentation

For every proposed slice provide:
- user-visible outcome
- evidence
- affected roles
- routes/components/services likely involved
- exact wording changes where relevant
- behavior that must remain unchanged
- important break cases
- acceptance criteria
- manual verification
- automated regression coverage
- dependencies
- collision risk
- external/client gate
- recommended execution order
- risk classification

Classify each finding:
- FIX
- DEFER
- DISMISS
- OWNER DECISION
- EXTERNAL INPUT

Finish with:
1. Top ten highest-value changes
2. Dependency-safe delivery sequence
3. Quick wins versus structural work
4. Items that must not be implemented without client authority
5. Definition of done for the complete cleanup pass
```

This gives you broad coverage without asking one model to understand the entire codebase, edit copy, map workflows, and write the client document in a single overloaded session.

