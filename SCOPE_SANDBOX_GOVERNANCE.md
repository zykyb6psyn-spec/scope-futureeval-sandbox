# SCOPE | FutureEval Sandbox Governance

## Status

This repository is an **Innovation Quarantine / technical sandbox**. It is not a formal SCOPE validation stream and it does not provide evidence of SCOPE predictive skill by itself.

## Current permitted use

The hardened smoke-test path may target **only** `bot-testing-area`.

The current configuration must keep:

- `scored_submission.enabled = false`
- `scope_preregistration.json -> scored_run_enabled = false`
- `scope_preregistration.json -> status = NOT_FROZEN`
- `models.researcher = no_research`

Any violation must fail closed before a forecast call is made.

## Separation from SCOPE validation

No output from this sandbox may directly alter an active probability, deadline, resolution criterion, evidence weight, benchmark definition or model parameter in SCOPE | AKT Validation or SCOPE | XVG Edge Watch.

External lessons return only through the Innovation Quarantine process and may be considered for a later SCOPE version or a newly pre-registered validation cycle.

## Audit requirements

Every technical smoke-test run must preserve an artifact containing at least:

1. a pre-run manifest;
2. the canonical configuration and preregistration hashes;
3. SHA-256 hashes of tracked source/configuration/dependency files;
4. GitHub run provenance including commit SHA and run ID;
5. a hash-chained forecast-report ledger;
6. a post-run manifest and final SHA-256 summary.

Runtime artifacts are evidence of technical execution only and must not be interpreted as performance validation.

## Gate for a future scored run

A scored FutureEval run must **not** reuse the current smoke-test configuration. Before exposure to the scored question set, a separate future cycle must be created and frozen with:

- target cycle / tournament / MiniBench identifier;
- information cut-off timestamp;
- exact Git commit SHA;
- exact configuration hash;
- exact code hash and dependency-lock hash;
- frozen model/provider routing and inference parameters;
- research-routing policy;
- aggregation method;
- scoring metrics and comparison baselines;
- question-selection rule;
- explicit statement that no tuning may occur after scored-question exposure.

Only after that preregistration is complete may a dedicated scored workflow be created. The current `scope_smoke_test.py` must remain unable to submit to a scored target.

## Secrets and permissions

API credentials must remain in GitHub Actions Secrets and must never be committed to the repository, printed to logs or copied into audit artifacts.

The smoke-test workflow uses read-only repository permissions and no workflow in this hardened path is scheduled automatically.

## Change discipline

Material sandbox changes should be made through a dedicated branch/pull request so that the change set, rationale and merge commit remain reconstructable. A successful smoke test after a change is a technical acceptance check, not a forecasting-performance result.
