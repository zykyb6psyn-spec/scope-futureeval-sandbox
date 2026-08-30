# SCOPE Benchmark Arm Specification v0.1

## Status

DESIGN DRAFT — NOT FROZEN

This document defines the intended symmetry and deliberate asymmetry between the SCOPE arm and its matched control for the first FutureEval performance cycle.

## Experimental question

Does SCOPE's structured forecasting method improve forecast quality when the underlying model, question snapshot, evidence packet, information cutoff and nominal compute envelope are held constant?

## Shared pipeline

Both arms receive an immutable `QuestionSnapshot` containing:

- Metaculus question ID and subquestion ID where applicable;
- question text;
- background text;
- resolution criteria;
- fine print;
- question type and answer bounds/options;
- open/close timestamps;
- first-seen UTC timestamp;
- information-cutoff UTC timestamp;
- a shared evidence packet hash.

Both arms must be generated before either arm can inspect the other's output.

## Shared evidence packet

For Cycle 1, external information retrieval, if enabled, is performed once upstream and the identical timestamped evidence packet is supplied to both arms.

The packet must contain:

- source identifier;
- source URL or durable source reference;
- retrieval timestamp;
- publication timestamp where available;
- verbatim factual observation or compact normalized fact;
- provenance class;
- question relevance tag;
- content hash.

The evidence generator is not part of the SCOPE-vs-control treatment effect in Cycle 1. Its purpose is to equalize information access.

Community Prediction, leaderboard information, other bot forecasts and the paired arm forecast are prohibited inputs.

## Arm A: SCOPE structured reasoning

Cycle 1 activates the following SCOPE components in a fixed order.

### 1. Evidence classification

For each evidence item, classify at minimum:

- direct / indirect;
- independent / dependent;
- confirmed fact / claim / inference;
- positive / negative / neutral with respect to the outcome;
- timestamp relevance.

No new evidence may be invented by the reasoning arm.

### 2. Dependency mapping

Identify dependencies that could cause multiple signals to reflect the same underlying event. Avoid double-counting correlated evidence.

Output a compact dependency representation sufficient to justify weighting decisions.

### 3. Base-rate anchor

State the most relevant reference class or explain why no defensible reference class is available.

The base rate is an anchor, not a mandatory final probability.

### 4. Scenario decomposition

Identify at least:

- status quo / continuation path;
- principal path toward the positive/high outcome;
- principal path toward the negative/low outcome;
- one plausible surprise path where relevant.

### 5. Probability synthesis

Produce the forecast from the evidence, dependency map, base-rate anchor and scenarios.

The arm must explicitly guard against:

- double-counting;
- unsupported precision;
- overreaction to a single vivid signal;
- unjustified extreme probabilities;
- treating absence of public evidence as evidence of absence unless the protocol supports that inference.

### 6. Calibration guard

Before finalizing, perform a fixed self-check:

- Would the forecast be meaningfully different if the strongest single signal disappeared?
- Is the confidence level consistent with evidence independence and time remaining?
- Is the probability more extreme than the evidence warrants?

The self-check may revise the forecast once, within the same model call if technically possible.

## Arm B: matched control

The control uses a standard professional-forecaster prompt that asks the same base model to:

- interpret the question;
- consider the supplied evidence packet;
- reason about plausible outcomes;
- provide a sincere probability/distribution.

The control prompt must not contain SCOPE-specific instructions concerning evidence classes, dependency mapping, explicit base-rate forcing, signal weighting or calibration guards.

The control may use ordinary forecasting concepts that are already part of the base template, such as considering the status quo and alternative scenarios.

## Model parity

Before freeze, record for both arms:

- provider and exact model identifier;
- temperature;
- top-p if used;
- seed if supported;
- maximum output tokens;
- timeout and retry policy;
- parser/formatter model if separate.

Default Cycle 1 rule:

- same base reasoning model in both arms;
- one core reasoning invocation per arm per question;
- same parser/formatter path;
- same evidence packet;
- same nominal maximum output-token allowance.

If SCOPE needs materially more compute to express its reasoning, actual cost and latency are retained as secondary outcomes rather than retrospectively equalized.

## Output parity

Both arms must produce the same machine-readable forecast schema required by the question type.

At minimum each record stores:

- arm;
- raw model output hash;
- parsed forecast;
- parse status;
- rationale hash;
- generation start/end timestamps;
- model/config hash;
- evidence packet hash;
- error/retry record.

## Ordering and blinding

Preferred execution order is randomized per question between SCOPE and control, using a pre-frozen deterministic seed, to minimize systematic provider-load or timing effects.

The second arm must not receive the first arm's forecast or rationale.

## First-cycle scope boundary

Cycle 1 does **not** test:

- SCOPE dynamic probability updating;
- social/market monitoring;
- specialized SCOPE Data Core domains;
- adaptive learning from target-cycle outcomes;
- human-in-the-loop intervention after question exposure.

Those capabilities require separate later protocols. This deliberate narrowing makes the first causal question interpretable: does structured SCOPE reasoning itself add forecast value?

## Required implementation evidence before freeze

- unit tests for input parity;
- test proving the other arm's output is not present in prompts;
- test proving CP/leaderboard fields are absent;
- deterministic prompt/config hashes;
- parser compatibility across all supported question formats;
- successful dry run on non-target test questions;
- scoring implementation validation against known examples;
- audit ledger capable of chaining paired records.

## Current state

No Cycle 1 arm implementation is frozen by this document. This is a design specification only.
