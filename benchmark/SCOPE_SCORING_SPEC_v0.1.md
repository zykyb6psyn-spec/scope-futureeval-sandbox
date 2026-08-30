# SCOPE Scoring & Statistics Specification v0.1

## Status

DESIGN DRAFT — NOT FROZEN — SCORED GATE CLOSED

This document defines the candidate scoring and statistical analysis layer for SCOPE FutureEval Cycle 1. It must be frozen before a scored target is bound.

## Primary estimand

For every resolved paired question `i`:

`Delta_i = log_score_SCOPE_i - log_score_CONTROL_i`

The primary Cycle-1 effect is:

`Delta_primary = mean(Delta_i)`

Natural logarithms are used, so the unit is **nats**. Higher is better.

A useful interpretation is:

`exp(Delta_primary)`

which is the geometric-mean likelihood/density ratio that SCOPE assigned to the realized outcomes relative to control.

Examples:

- `Delta = 0`: equal forecast performance.
- `Delta = ln(2) ≈ 0.693`: SCOPE assigned twice as much probability/density to the realized outcome as control.
- `Delta = -ln(2) ≈ -0.693`: SCOPE assigned half as much.

## Why a paired log-score difference

Metaculus uses proper log scoring for binary and multiple-choice forecasts and a continuous log-density score for continuous questions. FutureEval explicitly uses proper probabilistic scoring across binary, multiple-choice and numeric formats.

A paired difference has three advantages for this experiment:

1. It directly tests the incremental value of SCOPE over the matched control.
2. Question-specific constants and continuous-density units cancel inside the pair.
3. The same conceptual estimand can be aggregated across categorical and continuous question formats without relying on leaderboard composition.

Official Metaculus Peer/tournament scores remain important external descriptive benchmarks but are not the primary paired endpoint.

## Categorical questions

### Binary

For a Yes-probability `p`:

- if Yes resolves: `log_score = ln(p)`
- if No resolves: `log_score = ln(1-p)`

### Multiple choice

If option `k` resolves and the forecast assigned it probability `p_k`:

`log_score = ln(p_k)`

The paired delta is the difference between SCOPE and control log scores.

## Numeric, date and discrete questions

The frozen forecasting pipeline serializes the final **Metaculus-compatible standardized CDF** produced by `forecasting-tools`.

`forecasting-tools` standardization already applies the platform-style minimum mass behavior, open/closed bound handling, monotonicity constraints and PMF cap before publication.

### In-bound continuous/date outcome

Let the resolved value fall in CDF grid bucket `j`.

`bucket_mass = CDF[j+1] - CDF[j]`

On the fixed question grid, density is `bucket_mass / bucket_width`. Because both arms use the same question grid, `bucket_width` is identical and cancels in the paired log-density difference:

`Delta_i = ln(bucket_mass_SCOPE) - ln(bucket_mass_CONTROL)`

This remains valid for log-scaled questions because the comparison is made on the same standardized CDF-location grid.

### Discrete outcome

For discrete questions, the CDF difference is the PMF mass assigned to the realized discrete outcome, so the same log-mass calculation applies directly.

### Out-of-bound resolution

Consistent with Metaculus' documented rule that out-of-bound continuous resolutions are scored like binary events:

- below lower bound: use `CDF[0]`
- above upper bound: use `1 - CDF[-1]`

## Zero mass

A true zero mass is a catastrophic log-score error. The implementation does not silently alter the forecast. For computational finiteness only, `1e-15` is used when taking a logarithm of an exact zero, while the original zero remains visible in the score record.

Before freeze, forecast generation must be checked to ensure this computational sentinel is not routinely activated.

## Eligible formats for Cycle 1

Supported:

- binary
- multiple choice
- numeric
- discrete
- date

Excluded from Cycle 1:

- conditional questions

This explicit list corrects the format-label mismatch discovered during the first paired bot-testing-area dry run. The SCOPE treatment already has dedicated binary, multiple-choice, numeric and date prompts; discrete questions inherit the numeric treatment through `forecasting-tools`' `DiscreteQuestion(NumericQuestion)` model.

## Primary uncertainty analysis

Cluster bootstrap over independent parent-question/question-group clusters.

Frozen candidate parameters:

- resamples: `10,000`
- deterministic seed: `640064`
- report observed mean and median paired delta
- report 80% bootstrap interval
- report 95% bootstrap interval
- report `P(mean Delta > 0)`

Question-group subquestions are kept as separate scored rows but share one cluster identifier.

## Minimum evidence gates

A Cycle-1 performance classification requires at least:

- `30` resolved paired questions; and
- `20` independent clusters.

Below either threshold, the cycle is automatically classified as `INCONCLUSIVE_INSUFFICIENT_RESOLUTION` regardless of the observed point estimate.

These are interpretation gates rather than claims of formal statistical power.

## Technical failure gate

If generation failures exceed `5%` of eligible paired questions, no positive primary performance classification is allowed. The result becomes `INCONCLUSIVE_TECHNICAL_FAILURE_RATE` until the failure pattern is analyzed.

Failed cases are never silently removed.

## Interpretation thresholds

### Strong positive signal

- mean paired delta > 0
- bootstrap `P(mean Delta > 0) >= 0.90`
- generation failure rate <= 5%
- minimum evidence gates satisfied
- no tail-safety breach

### Promising signal

- mean paired delta > 0
- bootstrap `P(mean Delta > 0) >= 0.75` and < 0.90
- generation failure rate <= 5%
- minimum evidence gates satisfied
- no tail-safety breach

### Negative signal

- mean paired delta < 0; and
- bootstrap `P(mean Delta > 0) <= 0.25`

### Inconclusive

All other cases unless a specific technical or tail-risk classification applies.

## Catastrophic relative-tail guard

A paired outcome is a **catastrophic relative loss** when:

`Delta_i <= -3.0 nats`

This means SCOPE assigned no more than `exp(-3) ≈ 5%` of the realized-outcome probability/density assigned by control.

A symmetric relative win is `Delta_i >= +3.0 nats`.

A tail-safety breach occurs when:

- catastrophic relative loss rate > 5%; and
- loss rate exceeds catastrophic relative win rate by more than 5 percentage points.

If a tail breach occurs with mean advantage <= `0.10 nats`, classify `NEGATIVE_TAIL_RISK`.

If a tail breach occurs despite a larger positive mean, classify `INCONCLUSIVE_TAIL_RISK`. A positive mean may not override the predeclared tail guard.

## Secondary metrics

- median paired log-score difference
- per-question SCOPE win/tie/loss rate
- worst paired delta and 10th-percentile delta
- binary mean Brier score by arm and difference
- binary calibration diagnostics, added before freeze if sample size permits
- generation failure rate
- runtime, token and cost metrics
- official FutureEval / Metaculus score and rank for the submitted SCOPE arm

## Platform-parity validation requirement

The algebraic and synthetic validation suite is necessary but not sufficient for freeze.

Before the preregistration status can become `FROZEN_UNBOUND`, the scoring implementation must additionally be checked against resolved official Metaculus examples or an official scoring output/API path for all supported formats where such comparison is available.

The resulting validation record and its SHA-256 must be frozen in the preregistration.

## Reproducibility

Frozen scoring evidence must include hashes for:

- `scope_scoring.py`
- `scope_statistics.py`
- `scope_scoring_validation.py`
- this specification
- the platform-parity validation record
- the final analysis adapter that maps resolved Metaculus questions to score records

## Public methodology references

- Metaculus Scores FAQ: https://www.metaculus.com/help/scores-faq/
- Metaculus FutureEval Methodology: https://www.metaculus.com/futureeval/methodology/
- forecasting-tools NumericDistribution implementation: https://github.com/Metaculus/forecasting-tools/blob/main/forecasting_tools/data_models/numeric_report.py

No scored execution is authorized by this specification.
