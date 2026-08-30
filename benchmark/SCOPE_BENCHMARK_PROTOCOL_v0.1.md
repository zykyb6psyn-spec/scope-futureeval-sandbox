# SCOPE Benchmark Protocol v0.1

## Status

DESIGN DRAFT — NOT FROZEN — SCORED GATE CLOSED

This protocol defines the first external performance-validation design for SCOPE after technical acceptance of the FutureEval sandbox. It must be frozen before exposure to the selected scored question set.

## Objective

Test whether the SCOPE reasoning framework adds measurable forecasting value beyond a matched base-language-model control under the same question, evidence and compute conditions.

The first cycle is deliberately narrower than a full production SCOPE deployment. It tests the incremental value of the structured SCOPE reasoning layer before testing the later dynamic monitoring/update engine.

## External benchmark environment

Preferred environment: the first eligible future Metaculus FutureEval MiniBench that opens after this protocol and the implementation are frozen.

Target-selection rule:

1. Do not use a MiniBench whose questions were already visible before freeze.
2. Select the first new MiniBench whose opening time is at least 24 hours after the freeze timestamp.
3. Record the tournament identifier only after the freeze commit exists.
4. No question-level inspection is permitted before freeze.

Rationale: MiniBench is designed by Metaculus as a rapid, roughly bi-weekly benchmark with about 60 automated questions, making it suitable for a first ex-ante external validation cycle.

## Experimental design

### Two-arm paired design

Every eligible question is forecast by two arms from the same immutable input snapshot.

**Arm A — SCOPE**

Uses the SCOPE reasoning sequence:

Evidence → Dependency → Base Rate → Probability → Benchmark → Outcome → Calibration → Learning

For this first cycle, Learning is disabled during the live evaluation. No resolved outcomes from the target cycle may modify the frozen forecasting logic until the cycle is formally closed.

**Arm B — Matched Control**

Uses the same base LLM family, model version, temperature, question snapshot, evidence packet, timing and nominal compute budget, but without SCOPE-specific decomposition, dependency mapping, base-rate forcing, evidence classification or calibration prompts.

Only Arm A is intended to be submitted to the external benchmark unless Metaculus explicitly permits the matched control as a separate non-conflicting benchmark entry. Arm B must always be generated and preserved as a shadow forecast.

## Information parity

To isolate SCOPE rather than information access:

- both arms receive the exact same question text, resolution criteria, fine print and timestamped metadata;
- both arms receive the exact same evidence packet if external research is enabled;
- both arms use the same information cutoff;
- the SCOPE arm may structure, weight and reason over the evidence differently, but may not receive extra sources unavailable to the control;
- neither arm may see the Metaculus Community Prediction, bot aggregate, leaderboard signal or the other arm's forecast before both forecasts are frozen.

Any difference in information access invalidates the paired comparison for that question.

## First-cycle mode: initial-forecast trial

The first external cycle tests initial forecast quality, not adaptive updating.

- one initial forecast per eligible question per arm;
- both forecasts generated from the same first-capture snapshot;
- target initial forecast latency: as soon as operationally possible after question retrieval;
- no forecast updates during the evaluation window for the internal paired experiment;
- if the external platform requires or incentivizes updates, any later external-only update must be recorded separately and excluded from the primary paired analysis.

A later Stage B may test SCOPE's dynamic evidence-update capability under a separately frozen protocol.

## Eligibility and exclusions

Primary rule: all questions supported by both frozen arms are included. No discretionary cherry-picking is allowed.

Permitted exclusions are only:

- question format unsupported by either frozen arm before the cycle opens;
- malformed or inaccessible question payload;
- platform-side failure that prevents both arms from receiving equivalent input;
- question annulment or non-resolution under the benchmark's own rules.

Every exclusion must be timestamped with a pre-defined reason code. Performance-based exclusion is forbidden.

Question-group subquestions remain separate scored observations, but statistical uncertainty must be clustered by their shared parent/group identifier where applicable.

## Primary hypothesis

H1: SCOPE has higher mean proper-score performance than the matched control on the frozen target cycle.

Primary estimand:

`Delta_primary = mean(score_SCOPE_i - score_CONTROL_i)`

where `score` is the pre-validated Metaculus-compatible proper score for the question format.

Higher is better.

The scoring implementation must be validated against official Metaculus scoring examples before the target cycle is selected.

## Secondary hypotheses

H2: SCOPE reduces large forecast errors relative to control.

H3: SCOPE improves calibration on the binary subset.

H4: SCOPE's external FutureEval performance is competitive with the field, measured descriptively by official Metaculus tournament/Peer metrics and rank.

H5: SCOPE's gain, if any, is not purchased with disproportionate cost or failure rate.

## Metrics

### Primary

- paired mean proper-score difference, SCOPE minus control;
- cluster bootstrap probability that the mean difference is greater than zero.

### Secondary

- paired median score difference;
- per-question win / tie / loss rate;
- lower-tail score comparison to detect catastrophic overconfidence;
- binary Brier score, where applicable;
- binary calibration curve and expected calibration error, reported descriptively;
- official Metaculus Peer/tournament score and rank for the submitted SCOPE arm;
- forecast generation failure rate;
- wall-clock time per question;
- estimated inference cost per question;
- token usage where available.

Official leaderboard position is a valuable external benchmark but is not the sole primary endpoint because it depends on the composition and timing of the competing field.

## Uncertainty analysis

Because related subquestions may be correlated, uncertainty must not assume every row is independent.

Default method:

- cluster bootstrap by independent parent question / question group;
- 10,000 bootstrap resamples;
- report median Delta, 80% interval and 95% interval;
- report `P(Delta_primary > 0)` from the bootstrap distribution.

No significance threshold may be changed after outcomes are observed.

## First-cycle interpretation thresholds

These thresholds classify evidence, not commercial readiness.

**Strong positive signal**

- Delta_primary > 0;
- P(Delta_primary > 0) >= 0.90;
- forecast failure rate <= 5%;
- no material deterioration in catastrophic-error tail versus control.

**Promising signal**

- Delta_primary > 0;
- P(Delta_primary > 0) >= 0.75 but < 0.90;
- failure rate <= 5%.

**Inconclusive**

- P(Delta_primary > 0) between 0.25 and 0.75, or sample/resolution coverage is insufficient for a stable interpretation.

**Negative signal**

- Delta_primary < 0 and P(Delta_primary > 0) <= 0.25; or
- SCOPE exhibits a materially worse catastrophic-error tail despite a small mean advantage.

A single MiniBench cannot by itself establish that SCOPE is generally superior. A positive first cycle justifies replication on a second, separately frozen cycle.

## Technical-failure rule

If more than 5% of eligible paired questions fail to produce valid forecasts from either arm, the cycle may still be reported, but no primary performance claim may be made. The failure pattern must be analyzed first.

Complete-case performance may be shown only as secondary analysis; failed cases may never be silently dropped.

## Freeze requirements

Before target selection, the freeze record must contain at minimum:

- protocol version and SHA-256;
- SCOPE arm code commit and hashes;
- control arm code commit and hashes;
- exact model route(s) and model identifiers;
- temperature and other generation parameters;
- prompt hashes;
- evidence/research source policy;
- information cutoff rule;
- question inclusion/exclusion rules;
- scoring implementation hash and validation record;
- bootstrap/statistical-analysis implementation hash;
- compute/token budget policy;
- secret names, but never secret values;
- runtime versions and dependency-lock hash;
- freeze UTC timestamp;
- deterministic target-selection rule.

Once frozen, no performance-relevant component may change for the target cycle.

## Leakage controls

Before freeze:

- do not inspect target-cycle questions;
- do not inspect target-cycle community forecasts;
- do not select questions manually;
- do not tune prompts on target questions;
- do not use target-cycle outcomes or partial resolutions.

After freeze and during the cycle:

- retain raw question snapshots and first-seen timestamps;
- retain both arm outputs before submission;
- hide one arm from the other;
- retain evidence packets and source timestamps;
- retain all exceptions and retries;
- do not alter frozen prompts or scoring logic.

## Reproducibility

Each forecast record must include:

- forecast ID;
- question ID / subquestion ID;
- first-seen timestamp;
- information-cutoff timestamp;
- arm identifier;
- model identifier;
- prompt/config hashes;
- evidence-packet hash;
- prediction object;
- rationale hash;
- latency;
- cost/tokens if available;
- prior record hash for append-only chaining.

## Separation from SCOPE development

During the target cycle, development may continue only on separate branches or later versions. The frozen evaluation branch may not be modified.

Any discovered bug must be classified before looking at performance:

- infrastructure-only and non-forecast-affecting;
- forecast-affecting.

A forecast-affecting bug invalidates the affected cycle for confirmatory claims unless the frozen protocol already specified the remediation path.

## Decision after Cycle 1

If strong or promising:

1. preserve the full cycle as immutable evidence;
2. replicate on a second fresh MiniBench with no outcome-driven prompt tuning to the validated core;
3. only after replication consider Stage B dynamic updating and wider external claims.

If inconclusive:

- repeat with the same core design unless a documented technical limitation clearly dominated the test.

If negative:

- diagnose by evidence class and question type;
- treat any redesign as a new model/version;
- never rewrite Cycle 1 as though the revised model had generated the original forecasts.

## Current gate

At protocol v0.1 design stage:

- status: DESIGN_DRAFT;
- target cycle: NONE;
- target questions inspected: NO;
- scored run enabled: NO;
- benchmark freeze: NOT PERFORMED.

No scored FutureEval execution is authorized by this document.

## Public methodology references used for design

- Metaculus FutureEval Methodology: https://www.metaculus.com/futureeval/methodology/
- Metaculus FutureEval Participate: https://www.metaculus.com/futureeval/participate/
- Metaculus MiniBench: https://www.metaculus.com/aib/minibench/
- Metaculus Scores FAQ: https://www.metaculus.com/help/scores-faq/
- Metaculus Competition Rules: https://www.metaculus.com/tournament-rules/
