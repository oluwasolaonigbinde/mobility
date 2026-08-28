# W4-03B-P4 local load and reproducibility evidence

## Scope

`python3 scripts/run_w403b_load_reproducibility.py` is a local, provider-neutral,
synthetic-only command. It models the confirmed Abuja cohort: 10 vehicles, five
advertisers and a nominal 92-day (three-month) period. Ten in-process samples
time-compress that cohort; they are not a staging run or three-month burn-in.

The command reports JSON only. It records nearest-rank p50/p95 latency and
sample count for Campaign Performance Analysis computation, governed
map/heatmap provenance validation, and report-worker CSV/PDF rendering. It also
records artifact-pair throughput. The 2,000 ms ceilings are synthetic local
regression ceilings, not approved production SLOs.

## Failure and reproducibility boundaries

Timeout, operation error, network attempt, percentile-ceiling breach, malformed
or drifted frozen input, and changed live-gate output return a sanitized failure.
The profiling and frozen-rendering paths block socket creation and perform zero
external/provider actions. The command uses the existing W4-03B journey's
callable local-build check and evaluator, preserving exactly the six ordered
`BLOCKED` live boundaries without invoking its text-emitting CLI.

The frozen fixture is hash-bound. The command performs the same measurement
calculation and report CSV/PDF render twice, requiring identical canonical
result hashes and artifact bytes. A changed input hash is rejected rather than
being regenerated as a new authority. The target-area provenance fixture is
also hash-bound before its governed heatmap validation runs.

This is deterministic synthetic evidence permitted by D23. It does not supply
an approved report method, legal/privacy approval, provider, permit, release
environment, staging evidence, physical device evidence or pilot burn-in.
