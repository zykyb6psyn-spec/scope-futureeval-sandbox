from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, asdict
from typing import Any


OUTCOME_ABOVE = "above_upper_bound"
OUTCOME_BELOW = "below_lower_bound"
MIN_POSITIVE = 1e-15


@dataclass(frozen=True)
class PairScore:
    forecast_id: str
    question_id: str
    cluster_id: str
    question_type: str
    scope_log_score: float
    control_log_score: float
    delta_log_score: float
    outcome_probability_scope: float
    outcome_probability_control: float
    binary_brier_scope: float | None = None
    binary_brier_control: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_probability(p: float, label: str) -> float:
    p = float(p)
    if not math.isfinite(p) or p < 0.0 or p > 1.0:
        raise ValueError(f"{label} must be finite and between 0 and 1, got {p}")
    return p


def _safe_log_probability(p: float) -> float:
    # A zero-probability forecast is a catastrophic error under log scoring.
    # We retain a finite computational sentinel instead of silently changing
    # the forecast. Any use of this floor is separately detectable from p==0.
    return math.log(max(float(p), MIN_POSITIVE))


def binary_outcome_probability(prediction_yes: float, resolution: bool) -> float:
    p_yes = _require_probability(prediction_yes, "binary prediction")
    return p_yes if bool(resolution) else 1.0 - p_yes


def multiple_choice_outcome_probability(prediction: dict[str, Any], resolution: str) -> float:
    options = prediction.get("predicted_options")
    if not isinstance(options, list) or not options:
        raise ValueError("multiple-choice prediction must contain predicted_options")

    probabilities: dict[str, float] = {}
    for item in options:
        name = str(item["option_name"])
        p = _require_probability(float(item["probability"]), f"probability for {name}")
        probabilities[name] = p

    total = sum(probabilities.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"multiple-choice probabilities must sum to 1, got {total}")
    if resolution not in probabilities:
        raise ValueError(f"resolution {resolution!r} not found in predicted options")
    return probabilities[resolution]


def _cdf_points(prediction: dict[str, Any]) -> tuple[list[float], list[float]]:
    points = prediction.get("declared_percentiles")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("numeric/date/discrete prediction requires declared_percentiles")

    values = [float(p["value"]) for p in points]
    heights = [_require_probability(float(p["percentile"]), "CDF height") for p in points]

    if any(values[i] >= values[i + 1] for i in range(len(values) - 1)):
        raise ValueError("CDF values must be strictly increasing")
    if any(heights[i] > heights[i + 1] for i in range(len(heights) - 1)):
        raise ValueError("CDF heights must be nondecreasing")
    return values, heights


def continuous_bucket_probability(prediction: dict[str, Any], resolution: float | str) -> float:
    """Return standardized probability mass in the resolution bucket.

    forecasting-tools serializes the final Metaculus-compatible CDF on the
    platform grid. For an in-bound continuous/date outcome, log density equals
    log(bucket_mass / common_bucket_width). In a paired comparison on the same
    question, the bucket-width term cancels exactly, so the log-score difference
    is the log ratio of the two standardized bucket masses.

    For discrete questions the same CDF differences are the PMF masses.
    Out-of-bound outcomes are scored with their explicit tail mass.
    """
    values, heights = _cdf_points(prediction)
    lower = float(prediction["lower_bound"])
    upper = float(prediction["upper_bound"])

    if resolution == OUTCOME_BELOW:
        return heights[0]
    if resolution == OUTCOME_ABOVE:
        return 1.0 - heights[-1]

    outcome = float(resolution)
    if outcome < lower:
        return heights[0]
    if outcome > upper:
        return 1.0 - heights[-1]

    # Boundary semantics from forecasting-tools:
    # cdf[0] = P(Y < lower), so Y == lower belongs to the first inbound bucket.
    # cdf[-1] = P(Y <= upper), so Y == upper belongs to the last inbound bucket.
    if outcome <= values[0]:
        idx = 0
    elif outcome >= values[-1]:
        idx = len(values) - 2
    else:
        idx = bisect.bisect_right(values, outcome) - 1
        idx = max(0, min(idx, len(values) - 2))

    mass = heights[idx + 1] - heights[idx]
    if mass < -1e-12:
        raise ValueError(f"negative CDF bucket mass {mass}")
    return max(0.0, mass)


def outcome_probability(question_type: str, prediction: Any, resolution: Any) -> float:
    if question_type == "binary":
        return binary_outcome_probability(float(prediction), bool(resolution))
    if question_type == "multiple_choice":
        return multiple_choice_outcome_probability(prediction, str(resolution))
    if question_type in {"numeric", "date", "discrete"}:
        return continuous_bucket_probability(prediction, resolution)
    raise ValueError(f"unsupported scored question type: {question_type}")


def binary_brier(prediction_yes: float, resolution: bool) -> float:
    p = _require_probability(prediction_yes, "binary prediction")
    y = 1.0 if resolution else 0.0
    return (p - y) ** 2


def score_pair(record: dict[str, Any]) -> PairScore:
    required = [
        "forecast_id",
        "question_id",
        "cluster_id",
        "question_type",
        "resolution",
        "scope_prediction",
        "control_prediction",
    ]
    missing = [key for key in required if key not in record]
    if missing:
        raise ValueError(f"missing score-record fields: {missing}")

    qtype = str(record["question_type"])
    resolution = record["resolution"]
    p_scope = outcome_probability(qtype, record["scope_prediction"], resolution)
    p_control = outcome_probability(qtype, record["control_prediction"], resolution)

    scope_log = _safe_log_probability(p_scope)
    control_log = _safe_log_probability(p_control)

    brier_scope = None
    brier_control = None
    if qtype == "binary":
        brier_scope = binary_brier(float(record["scope_prediction"]), bool(resolution))
        brier_control = binary_brier(float(record["control_prediction"]), bool(resolution))

    return PairScore(
        forecast_id=str(record["forecast_id"]),
        question_id=str(record["question_id"]),
        cluster_id=str(record["cluster_id"]),
        question_type=qtype,
        scope_log_score=scope_log,
        control_log_score=control_log,
        delta_log_score=scope_log - control_log,
        outcome_probability_scope=p_scope,
        outcome_probability_control=p_control,
        binary_brier_scope=brier_scope,
        binary_brier_control=brier_control,
    )
