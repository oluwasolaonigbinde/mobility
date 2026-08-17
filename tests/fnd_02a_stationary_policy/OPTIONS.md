# FND-02A option contracts

## Choice A — rolling displacement

### Meaning

Classify normalized rolling windows by **net displacement over a selected
window**, not by whether each individual interval looks slow. A window is
stationary when displacement is **less than or equal to** the selected minimum.
This directly protects slow creeping traffic when its cumulative displacement
is meaningful, while repeated stop/hop windows can be classified stationary.

To make jitter deterministic, the owner must set consecutive confirmation and
release counts. Confirmation backdates to the first window in the qualifying
run; release backdates to the first window in the release run. This prevents the
chosen counts from silently gifting or confiscating an unrecorded prefix.

### Option-A parameters

| Symbol / template field | Unit/type | Scope/reset boundary | Inclusivity | Gap/missing behavior | Version timing |
|---|---|---|---|---|---|
| `RD_WINDOW_S` / `rolling_window_seconds` | seconds, positive | Rolling observation window within one trip or one Lagos day, per `RD_RESET_SCOPE`. | Window edges are `[start, end)`; exact elapsed boundary is included in the completed window. | A gap prevents a window spanning the unknown interval. | Frozen in `ELIGIBILITY_REVISION`. |
| `RD_MIN_DISPLACEMENT_M` / `minimum_net_displacement_m` | metres, positive | Compared with net displacement of each completed rolling window. | `displacement <= RD_MIN_DISPLACEMENT_M` is stationary; equality is stationary. | Invalid signal contributes no displacement evidence. | Frozen and fingerprinted. |
| `RD_CONFIRM_WINDOWS` / `confirmation_windows` | integer windows, positive | Consecutive stationary windows required. Confirmation backdates to run start. | Equality windows count toward confirmation. | Reset on `gps_gap`; not reset by area/window exclusion. | Frozen and explained. |
| `RD_RELEASE_WINDOWS` / `release_windows` | integer windows, positive | Consecutive above-threshold windows required to release stationary state. Release backdates to run start. | Only `>` counts toward release. | Reset on `gps_gap`. | Frozen and explained. |
| `RD_RESET_SCOPE` / `reset_scope` | `trip` or `lagos_day` | `trip`: state can cross Lagos midnight. `lagos_day`: state starts fresh at Africa/Lagos midnight. Session start always resets. | Exact midnight belongs to the new Lagos day. | Area/window boundaries never reset. | Owner must select one. |
| `gps_gap_state` | fixed enum | `reset_detector` | Not variable. | Gap interval is excluded and rolling state restarts after it. | Recorded in revision metadata. |

### Expected user explanation

- Payable: `moving_rolling_displacement_above_threshold`.
- Excluded after shared grace:
  `stationary_rolling_displacement` with window, displacement boundary,
  confirmation/release counts and revision visible.
- Held/review: none from this policy.

## Choice B — cumulative sub-window stationary budget

### Meaning

Keep the existing long-stay detector and one whole-scope grace. Separately sum
all **short stationary candidate time** where episode duration is strictly
below `SW_S`, including candidates separated by radius-breaking hops. The first
`CSB_BUDGET_S` seconds are payable; only time **strictly above** that cumulative
budget is excluded. Equality is payable.

This closes the renewable short-stop loophole without requiring a rolling
movement threshold, but it makes the honest-congestion trade-off explicit:
slow traffic can consume the same budget unless the owner chooses sufficient
allowance.

### Option-B parameters

| Symbol / template field | Unit/type | Scope/reset boundary | Inclusivity | Gap/missing behavior | Version timing |
|---|---|---|---|---|---|
| `CSB_BUDGET_S` / `cumulative_budget_seconds` | seconds, non-negative | One cumulative allowance per `CSB_SCOPE`. Hops, out-of-area and out-of-window slices do not replenish it. | Candidate time `<= CSB_BUDGET_S` is payable; only `>` is excluded. | Invalid signal contributes no candidate evidence. | Frozen and fingerprinted. |
| `CSB_SCOPE` / `budget_scope` | `trip` or `lagos_day` | `trip`: one allowance for the full trip. `lagos_day`: new allowance exactly at Africa/Lagos midnight. | Exact midnight belongs to the new scope. | A gap ends positional continuity but does not restore spent budget. | Owner must select one. |
| `gps_gap_state` | fixed enum | `retain_spent_budget` | Not variable. | Gap interval is excluded; prior spent remains. | Recorded in revision metadata. |

### Expected user explanation

- Payable short-stop time: `stationary_subwindow_budget_available` with
  remaining allowance.
- Excluded: `stationary_subwindow_budget_exceeded` with cumulative seconds,
  budget, scope and revision.
- Held/review: none from this policy.

## Choice C — explicit fraud deferral / hold

### Meaning

Do **not** convert the short pattern into permanently unpaid time. Accumulate
short-stay seconds and unique episode count as fraud evidence. When the selected
inclusive trigger fires, hold every otherwise payable second in the selected
scope for authoritative review. Existing signal/window/area and long-stay
exclusions still apply.

This is structurally consistent with D5/Q21, but it is **not immediately
implementable as an RM2 closure**. The repository currently lacks the required
MNY-08A/B current assessment, serialized state machine and shared
`hold_active` money predicate. The option-C template therefore records
`hold_infrastructure_ready: false`, and the evaluator refuses to run until that
fact is explicitly changed in a test/decision environment. FND-02B alone must
not simulate a release hold with a local flag or duplicate predicate.

Follow-up ownership for option C maps to the §35.1 RM9 register row
(fraud-rule compensating controls) in addition to the MNY-08A/B hold
infrastructure dependency. The pilot-tuning path is explicit: the selected
thresholds enter as reviewable configuration, pilot evidence feeds RM9 tuning,
and any later tightening becomes a new policy revision under the same D14
discipline — never a silent change.

### Option-C parameters

| Symbol / template field | Unit/type | Scope/reset boundary | Inclusivity | Gap/missing behavior | Version timing |
|---|---|---|---|---|---|
| `HOLD_SECONDS_TRIGGER_S` / `hold_candidate_seconds_trigger` | seconds, positive | Cumulative valid short-candidate evidence per `HOLD_SCOPE`. | `candidate_seconds >= trigger` fires. | Gap does not erase prior evidence; gap itself contributes none. | Frozen in fraud assessment + eligibility revisions. |
| `HOLD_EPISODE_TRIGGER` / `hold_episode_count_trigger` | unique episodes, positive integer | Counts unique short episodes in scope; radius-breaking hops create new episodes. | `episode_count >= trigger` fires. | Invalid signal does not create an episode. | Frozen and fingerprinted. |
| `HOLD_TRIGGER_LOGIC` / `trigger_logic` | `any` or `all` | `any`: either threshold fires. `all`: both must fire. | Equality satisfies each predicate. | Not reset by area/window exclusion or GPS gap. | Owner must select one. |
| `HOLD_SCOPE` / `hold_scope` | `trip` or `lagos_day` | Trigger retroactively holds all otherwise payable seconds in that scope. | Exact midnight belongs to the new Lagos-day scope. | Evidence carries across gap inside the same selected scope. | Owner must select one. |
| `FRAUD_ASSESSMENT_VERSION` / `fraud_assessment_version` | immutable stable ID | Identifies evidence formula and trigger set consumed by MNY-08A/B. | Missing ID fails closed. | Errors/stale assessment remain held, never silently clean. | Effective with the bound eligibility revision. |
| `gps_gap_state` | fixed enum | `retain_evidence` | Not variable. | Retains evidence but never infers movement through the gap. | Recorded in assessment metadata. |
| `hold_infrastructure_ready` | boolean capability fact | Must be `true` only after MNY-08A/B is integrated and verified. | `false` causes evaluator refusal. | Not a policy threshold. | Currently `false`. |

### Expected user explanation

- Gross payable: existing classifier result, with base/premium tier.
- Held: `stationary_pattern_hold_pending_review`, including sanitized evidence
  summary and assessment revision.
- Released: zero for the triggered scope until authoritative dismissal/release.
- Excluded: unchanged existing reason codes; option C does not pretend held time
  is permanently unpaid.

