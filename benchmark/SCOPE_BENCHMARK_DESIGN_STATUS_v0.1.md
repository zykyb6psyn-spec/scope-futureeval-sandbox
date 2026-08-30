# SCOPE Benchmark Design v0.1 — Status Record

## Status

PAIRED TECHNICAL DRY RUN: PASSED

SCORING + STATISTICS LAYER: PASSED OFFLINE VALIDATION

IMMUTABLE QUESTION IDENTITY + RESOLUTION ADAPTER: PASSED

SCORED BENCHMARK: NOT AUTHORIZED

TARGET CYCLE: UNBOUND

## Reference branch

- Design branch: `scope-benchmark-design-v0.1`
- Accepted technical sandbox base: `edfdfb2284a6b1702227f37f95549ba20bf3bdd5`
- This branch remains development/quarantine only. It is not a scored evaluation branch.

## Latest paired identity dry-run

The latest forecast-affecting paired dry run executed only against Metaculus `bot-testing-area` with publishing disabled.

- workflow: `SCOPE Benchmark Paired Dry Run`
- workflow run ID: `33340906275`
- run conclusion: `success`
- workflow head SHA: `c187cfa2e5b939934e96236b5a08df8b42c32a81`
- questions retrieved: 9
- paired supported questions: 9
- exclusions: 0
- SCOPE arm failures: 0
- matched-control failures: 0
- paired ledger tip SHA-256: `f260c948732fbc7d82ad15cbc45fe34c754052af47b36cfb5b822b9e62e013c1`
- paired manifest SHA-256: `72efc9cafceec7722ff2ebd72595c3508eb55c7fd08a6aa53ed8175c7ca9b6fe`

### Identity verification

All nine paired records contain non-empty:

- immutable Metaculus `question_id` (`id_of_question`);
- `post_id` (`id_of_post`);
- conservative statistical `cluster_id = post:<post_id>`.

All 9 question IDs are unique.

The artifact empirically confirms why URL-based joining is forbidden: at least two post URLs in the bot-testing-area each contained two distinct subquestions with different immutable question IDs. The post ID is therefore suitable as a conservative dependency cluster, but not as the unique scoring key.

### Paired dry-run artifact

- artifact name: `scope-benchmark-paired-dryrun-33340906275-1`
- artifact ID: `9740536457`
- artifact ZIP SHA-256: `129c5aa70b1a35b32cffd35c6c804d1c8bd46504ab14602ba0d84ab00fe80ade`
- retention: 30 days

## Scoring and statistical layer

Cycle 1 now has a single candidate primary estimand:

`Delta_i = ln(p_SCOPE(realized_i)) - ln(p_CONTROL(realized_i))`

and

`Delta_primary = mean(Delta_i)`

in natural-log units (nats), higher is better.

For binary and multiple-choice questions, `p(realized)` is the probability assigned to the resolved outcome. For numeric/date/discrete questions it is the official Metaculus-compatible PMF resolution bucket derived from the final standardized CDF.

The implementation mirrors the relevant probability/PMF semantics from the open-source Metaculus backend, including:

- categorical resolved-option probability;
- continuous/date/discrete CDF-to-PMF conversion;
- exact grid-boundary mapping;
- log-scaled numeric location mapping;
- out-of-bound tail mass;
- multiple-choice `Other` fallback for a later-added resolution option.

### Offline validation

- workflow: `SCOPE Scoring Validation`
- final validation run ID: `33341020190`
- run conclusion: `success`
- workflow head SHA: `848ce403f0ea27db00e6f63691e65a0b67bd2b97`
- validation tests: 19
- validation record SHA-256: `bc3beb702c2939fa458f0a09bf1ffc4851deb2d2b427c9a4a2231f45e3dfa0d8`
- artifact ID: `9740537124`
- artifact ZIP SHA-256: `18d19ed1b72f8a4b258469aaf435aa7b5369ec326ebb8fee65d47f5546fdb664`
- retention: 90 days

Frozen-candidate implementation hashes recorded by the validation artifact:

- `scope_scoring.py`: `0191d4512ff16f05a4c9c658ce75cca3c7ea9b6caa54ee3b8dff1cf2a41bdd1c`
- `scope_statistics.py`: `0d8d853070f6bf6e44ff96acb22bf1229925baf4ca527a196f998407e441e359`
- `scope_resolution_adapter.py`: `9e1200845d202cdf7174249dadd2842b0f3274ee49107dd778d91f5931ec4b31`
- `scope_scoring_validation.py`: `2f1378298de43d6f1eeebf0ab11de88cbd7c98a77c42a58b47a4182145646a31`

These are design-stage evidence hashes. They are not yet the formal preregistration freeze hashes.

## Resolution adapter

The resolution adapter is fail-closed and joins forecasts to outcomes only by immutable question/subquestion ID.

It has explicit tests for:

- successful immutable-ID scoring joins;
- distinct subquestions sharing the same display URL;
- mismatched question IDs;
- non-resolved records with no usable resolution value;
- annulled resolutions;
- mandatory resolution source hash and capture timestamp.

Non-resolved or annulled cases become timestamped/auditable exclusions and are never silently dropped.

## Statistical interpretation gates

Candidate frozen parameters:

- cluster bootstrap: 10,000 resamples;
- deterministic seed: `640064`;
- minimum 30 resolved pairs;
- minimum 20 independent clusters;
- maximum generation-failure rate for a positive classification: 5%;
- catastrophic relative-loss threshold: `Delta <= -3.0 nats`;
- predeclared strong/promising/negative/inconclusive and tail-risk classifications.

These thresholds are now encoded in the offline-tested statistics implementation. They remain design-stage choices until formal freeze.

## Design gates still closed

At this milestone:

- preregistration status remains `DESIGN_DRAFT`;
- scored execution remains disabled;
- no scored target ID is selected;
- target binding remains `UNBOUND`;
- explicit scored authorization remains false;
- target-question inspection before freeze remains prohibited;
- Community Prediction and leaderboard signals remain prohibited inputs;
- performance-based exclusions remain forbidden.

## Interpretation boundary

These results validate the experimental plumbing, score mathematics, statistical rules and provenance path. They do **not** establish SCOPE predictive skill, calibration advantage, benchmark superiority or economic edge.

## Next required gates before freeze

1. Complete automated parity/leakage tests for the exact question snapshot supplied to both arms.
2. Complete freeze-readiness hashing for prompt, code, config, runtime, dependency and analysis assets.
3. Run the full `FROZEN_UNBOUND` gate in a dry verification mode without selecting a target.
4. Only after an explicit formal freeze may the predeclared 24-hour waiting rule begin.
5. Only after that delay may the first eligible future MiniBench be bound without inspecting its questions beforehand.
6. A separate scored authorization record must then explicitly authorize that one bound cycle.

No scored FutureEval execution is authorized by this status record.
