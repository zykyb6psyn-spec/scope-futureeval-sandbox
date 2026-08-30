# SCOPE FutureEval Sandbox v0.2.3

## Technical Acceptance Record

**Status: TECHNICALLY ACCEPTED**

This record documents the technical acceptance of the quarantined SCOPE FutureEval sandbox after the final hardened end-to-end acceptance run.

### Accepted build

- Sandbox version: `0.2.3`
- Accepted runtime commit: `edfdfb2284a6b1702227f37f95549ba20bf3bdd5`
- Workflow: `SCOPE FutureEval Smoke Test`
- GitHub Actions run ID: `33339294691`
- Run number: `5`
- Run conclusion: `success`
- Target: `bot-testing-area`

### Acceptance evidence

- Fail-closed integrity check: PASS
- Runner pinned to `ubuntu-24.04`
- Python pinned to `3.11.16`
- Poetry pinned to `2.4.2`
- Dependencies installed from committed `poetry.lock` via `poetry sync`
- Persisted checkout credentials disabled
- GitHub Actions dependencies pinned to immutable commit SHAs
- External research disabled: `researcher=no_research`
- Synthetic research summarization disabled: `enable_summarize_research=false`
- Research summary excluded from forecasting: `use_research_summary_to_forecast=false`
- Scored submission disabled and no scored targets allowed
- 9 forecast reports completed
- 0 forecast exceptions
- 0 minor report errors
- Technical publishing path exercised only against `bot-testing-area`

### Audit verification

- Pre-run canonical manifest SHA-256: `0e3ffbe28ded4c93780d3bcae67165a75e794df816312ba2ebbd8e1b245d0f33`
- Forecast ledger record count: `9`
- Ledger chain independently verified from `GENESIS` through all 9 records
- Ledger tip SHA-256: `a96aafa64f160012301c33c44d1bb00336b88b7c3c23cefb936f41417bce73d7`
- Audit artifact: `scope-futureeval-audit-33339294691-1`
- Audit artifact SHA-256: `f6f670160b8d6e1d0df869c7a8545e5c7c8306139b514432cf82be8ba36505b4`
- Audit artifact retention: 90 days

The SHA-256 entries for `pre_run_manifest.json`, `post_run_manifest.json`, and `forecast_ledger.jsonl` were independently checked against the downloaded acceptance artifact and matched exactly.

### Boundary of acceptance

This acceptance establishes that the sandbox plumbing, isolation gates, runtime reproducibility controls and audit trail operate successfully as designed.

It is **not** evidence of predictive skill, calibration quality, benchmark superiority or economic edge.

The scored-validation gate remains closed. At acceptance time:

- preregistration status: `NOT_FROZEN`
- `scored_run_enabled=false`
- no scored FutureEval target selected

Any later scored benchmark cycle must be separately preregistered and frozen before exposure to its target question set.

### Governance note

`main` remains on the exact accepted runtime commit. This acceptance record is intentionally stored on the dedicated branch `scope-technical-acceptance-v0.2.3` so that documenting acceptance does not mutate the build that was actually tested.