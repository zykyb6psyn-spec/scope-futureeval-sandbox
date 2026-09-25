# SCOPE Repository Status

**Repository:** `scope-futureeval-sandbox`  
**Status date:** 2026-09-25  
**Classification:** Innovation Quarantine / technical validation sandbox

## Boundary

This repository is retained as a reconstructable technical environment for FutureEval, Metaculus smoke testing, ForecastBench shadow work, hardening experiments and related validation mechanics.

It is **not** the canonical SCOPE codebase and must not evolve into the general SCOPE implementation repository.

## Permitted role

- preserve the historical technical validation trail;
- run explicitly authorized technical smoke tests;
- preserve audit, integrity and reproducibility controls;
- support isolated benchmark/shadow experiments under their own frozen rules.

## Prohibited role

Outputs from this repository must not directly rewrite or silently alter active SCOPE forecasts, evidence weights, deadlines, resolution criteria, benchmark definitions or model parameters.

Historical records remain append-only. Corrections or new validation cycles must be recorded as new, attributable events rather than retroactive edits.

## Automation boundary

The inherited Metaculus tournament and Cup workflows are retained for provenance but automatic schedule triggers are disabled. Manual execution does not override SCOPE governance, preregistration or target restrictions.

## Canonical SCOPE direction

The future canonical SCOPE technical implementation is to live in a separate private repository, currently designated `scope-core`. Only reviewed, reusable components may later move from this sandbox into that repository.

See `SCOPE_SANDBOX_GOVERNANCE.md` for the detailed sandbox rules.
