from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from scope_scoring import (
    OUTCOME_ABOVE,
    PairScore,
    binary_outcome_probability,
    continuous_bucket_probability,
    multiple_choice_outcome_probability,
    score_pair,
)
from scope_statistics import analyze_pairs, cluster_bootstrap_mean_delta


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "scoring_validation_output"
OUT.mkdir(exist_ok=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_close(actual: float, expected: float, tol: float = 1e-10) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tol):
        raise AssertionError(f"expected {expected}, got {actual}")


def simple_cdf(middle_height: float) -> dict:
    return {
        "declared_percentiles": [
            {"value": 0.0, "percentile": 0.0},
            {"value": 5.0, "percentile": middle_height},
            {"value": 10.0, "percentile": 1.0},
        ],
        "lower_bound": 0.0,
        "upper_bound": 10.0,
        "open_lower_bound": False,
        "open_upper_bound": False,
        "cdf_size": 3,
    }


def open_cdf() -> dict:
    return {
        "declared_percentiles": [
            {"value": 0.0, "percentile": 0.10},
            {"value": 5.0, "percentile": 0.50},
            {"value": 10.0, "percentile": 0.80},
        ],
        "lower_bound": 0.0,
        "upper_bound": 10.0,
        "open_lower_bound": True,
        "open_upper_bound": True,
        "cdf_size": 3,
    }


def make_pair(index: int, delta: float, cluster: str | None = None) -> PairScore:
    control = math.log(0.30)
    return PairScore(
        forecast_id=f"F-{index:03d}",
        question_id=f"Q-{index:03d}",
        cluster_id=cluster or f"C-{index:03d}",
        question_type="binary",
        scope_log_score=control + delta,
        control_log_score=control,
        delta_log_score=delta,
        outcome_probability_scope=math.exp(control + delta),
        outcome_probability_control=0.30,
        binary_brier_scope=0.10,
        binary_brier_control=0.12,
    )


def main() -> None:
    tests: list[str] = []

    assert_close(binary_outcome_probability(0.8, True), 0.8)
    assert_close(binary_outcome_probability(0.8, False), 0.2)
    tests.append("binary outcome probability")

    mc = {
        "predicted_options": [
            {"option_name": "A", "probability": 0.2},
            {"option_name": "B", "probability": 0.7},
            {"option_name": "C", "probability": 0.1},
        ]
    }
    assert_close(multiple_choice_outcome_probability(mc, "B"), 0.7)
    tests.append("multiple-choice outcome probability")

    assert_close(continuous_bucket_probability(simple_cdf(0.8), 2.0), 0.8)
    assert_close(continuous_bucket_probability(simple_cdf(0.8), 8.0), 0.2)
    tests.append("continuous inbound bucket mass")

    assert_close(continuous_bucket_probability(open_cdf(), -1.0), 0.10)
    assert_close(continuous_bucket_probability(open_cdf(), OUTCOME_ABOVE), 0.20)
    tests.append("continuous out-of-bound tail mass")

    record = {
        "forecast_id": "F-PAIR",
        "question_id": "Q-PAIR",
        "cluster_id": "C-PAIR",
        "question_type": "binary",
        "resolution": True,
        "scope_prediction": 0.8,
        "control_prediction": 0.4,
    }
    pair = score_pair(record)
    assert_close(pair.delta_log_score, math.log(2.0))
    tests.append("paired categorical log-score difference")

    numeric_record = {
        "forecast_id": "F-NUM",
        "question_id": "Q-NUM",
        "cluster_id": "C-NUM",
        "question_type": "numeric",
        "resolution": 2.0,
        "scope_prediction": simple_cdf(0.8),
        "control_prediction": simple_cdf(0.4),
    }
    numeric_pair = score_pair(numeric_record)
    assert_close(numeric_pair.delta_log_score, math.log(2.0))
    tests.append("paired continuous bucket log-density ratio")

    equal_pairs = [make_pair(i, 0.0) for i in range(30)]
    equal_boot_1 = cluster_bootstrap_mean_delta(equal_pairs, resamples=1000, seed=42)
    equal_boot_2 = cluster_bootstrap_mean_delta(equal_pairs, resamples=1000, seed=42)
    if equal_boot_1 != equal_boot_2 or any(x != 0.0 for x in equal_boot_1):
        raise AssertionError("cluster bootstrap must be deterministic and preserve all-zero deltas")
    tests.append("deterministic cluster bootstrap")

    positive_pairs = [make_pair(i, 0.20) for i in range(30)]
    positive = analyze_pairs(
        positive_pairs,
        eligible_pair_count=30,
        generation_failure_count=0,
        resamples=2000,
        seed=42,
    )
    if positive["interpretation_class"] != "STRONG_POSITIVE_SIGNAL":
        raise AssertionError(positive)
    assert_close(positive["mean_delta_nats"], 0.20)
    tests.append("strong-positive interpretation gate")

    negative_pairs = [make_pair(i, -0.20) for i in range(30)]
    negative = analyze_pairs(
        negative_pairs,
        eligible_pair_count=30,
        generation_failure_count=0,
        resamples=2000,
        seed=42,
    )
    if negative["interpretation_class"] != "NEGATIVE_SIGNAL":
        raise AssertionError(negative)
    tests.append("negative interpretation gate")

    insufficient = analyze_pairs(
        [make_pair(i, 0.5) for i in range(10)],
        eligible_pair_count=10,
        generation_failure_count=0,
        resamples=500,
        seed=42,
    )
    if insufficient["interpretation_class"] != "INCONCLUSIVE_INSUFFICIENT_RESOLUTION":
        raise AssertionError(insufficient)
    tests.append("minimum resolution gate")

    high_failure = analyze_pairs(
        positive_pairs,
        eligible_pair_count=40,
        generation_failure_count=10,
        resamples=500,
        seed=42,
    )
    if high_failure["interpretation_class"] != "INCONCLUSIVE_TECHNICAL_FAILURE_RATE":
        raise AssertionError(high_failure)
    tests.append("technical failure-rate gate")

    tail_pairs = [make_pair(i, 0.20) for i in range(27)] + [
        make_pair(27, -3.5),
        make_pair(28, -3.5),
        make_pair(29, -3.5),
    ]
    tail = analyze_pairs(
        tail_pairs,
        eligible_pair_count=30,
        generation_failure_count=0,
        resamples=1000,
        seed=42,
    )
    if not tail["tail"]["tail_safety_breach"]:
        raise AssertionError("tail safety breach was not detected")
    tests.append("catastrophic relative-tail gate")

    validation = {
        "schema_version": "1.0",
        "status": "PASS",
        "test_count": len(tests),
        "tests": tests,
        "implementation_hashes": {
            "scope_scoring.py": sha256_file(ROOT / "scope_scoring.py"),
            "scope_statistics.py": sha256_file(ROOT / "scope_statistics.py"),
            "scope_scoring_validation.py": sha256_file(ROOT / "scope_scoring_validation.py"),
        },
        "validated_properties": [
            "binary and multiple-choice correct-outcome probability",
            "numeric/date/discrete standardized CDF bucket scoring",
            "out-of-bound tail scoring",
            "paired log-score difference",
            "deterministic cluster bootstrap",
            "positive, negative, insufficient-sample, technical-failure and tail-risk gates",
        ],
        "external_reference_note": (
            "Metaculus documents log score as the proper score for categorical questions and "
            "continuous log score as log probability density, with standardized numeric CDFs "
            "including a uniform minimum-mass component. This validation suite tests the paired "
            "implementation algebraically; platform parity must still be checked against resolved "
            "official examples before preregistration freeze."
        ),
    }
    (OUT / "scoring_validation_record.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
