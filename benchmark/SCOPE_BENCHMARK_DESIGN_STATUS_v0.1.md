# SCOPE Benchmark Design v0.1 — Status Record

## Status

PAIRED TECHNICAL DRY RUN: PASSED

SCORED BENCHMARK: NOT AUTHORIZED

TARGET CYCLE: UNBOUND

## Reference build

- Design branch: `scope-benchmark-design-v0.1`
- Paired dry-run workflow: `SCOPE Benchmark Paired Dry Run`
- Workflow run ID: `33339988701`
- Run number: `1`
- Run conclusion: `success`
- Workflow head SHA: `cf328a47c69d85e6ae50310bd18664035aae9b1e`

## Paired dry-run result

The dry run executed only against Metaculus `bot-testing-area` with publishing disabled.

- questions retrieved: 9
- paired supported questions: 9
- exclusions: 0
- SCOPE arm failures: 0
- matched-control failures: 0
- paired ledger tip SHA-256: `815220393fe3f7e7c7c805a1526d3f2f70921fe3e15bdc5ac9c978535774222e`

The SCOPE arm and matched-control arm were supplied from the same retrieved question objects and were executed with publishing disabled. The control uses the upstream SummerTemplateBot2026 reasoning prompts. The SCOPE treatment uses the dedicated structured reasoning prompt path.

The paired technical run demonstrates operational separation of the two arms and successful parsing across the encountered supported question formats. It does not establish forecast superiority because the dry-run test questions are not the frozen scored target cycle.

## Design gates verified during the run

The fail-closed draft checker passed before forecasts were generated. At the time of the dry run:

- preregistration status remained `DESIGN_DRAFT`;
- scored execution remained disabled;
- no scored target ID was selected;
- target binding remained `UNBOUND`;
- explicit scored authorization remained false;
- target-question inspection before freeze remained prohibited;
- Community Prediction and leaderboard signals remained prohibited inputs;
- cross-arm forecast visibility remained prohibited;
- performance-based exclusions remained forbidden.

## Dry-run artifact

- artifact name: `scope-benchmark-paired-dryrun-33339988701-1`
- artifact ID: `9740265566`
- artifact ZIP SHA-256: `2473921fbb357842bde81fba14f483a3436de9e49511b9e7ff1f7eceb1249b5b`
- retention: 30 days

The artifact contains the paired dry-run manifest and preserves question-snapshot hashes, deterministic arm execution order, prediction hashes, explanation hashes, error state and the append-only paired ledger chain.

## Interpretation boundary

This is a technical and methodological design milestone only. No inference about SCOPE predictive skill, calibration advantage, benchmark superiority or economic edge is permitted from this run.

## Next required gates before freeze

1. Implement and validate a Metaculus-compatible local scoring layer against official scoring mathematics/examples.
2. Implement the frozen paired statistical analysis and cluster-bootstrap layer.
3. Add automated parity/leakage tests for question inputs and arm isolation.
4. Freeze exact prompt, config, runtime, dependency and analysis hashes.
5. Freeze the preregistration in `FROZEN_UNBOUND` state while the target remains unknown.
6. Only after the freeze and the predeclared waiting period may the first eligible future MiniBench be bound.
7. A separate scored authorization record must then explicitly authorize that one bound cycle.
