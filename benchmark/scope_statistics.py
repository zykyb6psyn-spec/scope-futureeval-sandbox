from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict
from typing import Any

import numpy as np

from scope_scoring import PairScore


BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 640064
MIN_RESOLVED_PAIRS = 30
MIN_INDEPENDENT_CLUSTERS = 20
MAX_GENERATION_FAILURE_RATE = 0.05
CATASTROPHIC_DELTA_NATS = 3.0
TAIL_RATE_TOLERANCE = 0.05
SMALL_MEAN_ADVANTAGE_NATS = 0.10
TIE_TOLERANCE_NATS = 1e-12


def _quantile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q))


def cluster_bootstrap_mean_delta(
    pairs: list[PairScore],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float]:
    if not pairs:
        raise ValueError("at least one resolved pair is required")
    if resamples <= 0:
        raise ValueError("resamples must be positive")

    grouped: dict[str, list[float]] = defaultdict(list)
    for pair in pairs:
        grouped[pair.cluster_id].append(pair.delta_log_score)

    cluster_ids = sorted(grouped)
    if not cluster_ids:
        raise ValueError("no clusters available")

    rng = np.random.default_rng(seed)
    draws: list[float] = []
    n_clusters = len(cluster_ids)

    for _ in range(resamples):
        sampled_indices = rng.integers(0, n_clusters, size=n_clusters)
        sample_values: list[float] = []
        for idx in sampled_indices:
            sample_values.extend(grouped[cluster_ids[int(idx)]])
        draws.append(float(np.mean(sample_values)))

    return draws


def _tail_metrics(deltas: list[float]) -> dict[str, Any]:
    catastrophic_losses = [d for d in deltas if d <= -CATASTROPHIC_DELTA_NATS]
    catastrophic_wins = [d for d in deltas if d >= CATASTROPHIC_DELTA_NATS]
    n = len(deltas)
    loss_rate = len(catastrophic_losses) / n if n else math.nan
    win_rate = len(catastrophic_wins) / n if n else math.nan
    tail_breach = bool(
        n
        and loss_rate > TAIL_RATE_TOLERANCE
        and (loss_rate - win_rate) > TAIL_RATE_TOLERANCE
    )
    return {
        "catastrophic_threshold_nats": CATASTROPHIC_DELTA_NATS,
        "catastrophic_relative_loss_count": len(catastrophic_losses),
        "catastrophic_relative_win_count": len(catastrophic_wins),
        "catastrophic_relative_loss_rate": loss_rate,
        "catastrophic_relative_win_rate": win_rate,
        "tail_safety_breach": tail_breach,
        "worst_delta_nats": min(deltas) if deltas else None,
        "best_delta_nats": max(deltas) if deltas else None,
        "p10_delta_nats": _quantile(deltas, 0.10) if deltas else None,
    }


def _classification(
    *,
    mean_delta: float,
    probability_gt_zero: float,
    generation_failure_rate: float,
    resolved_pairs: int,
    independent_clusters: int,
    tail_breach: bool,
) -> str:
    if resolved_pairs < MIN_RESOLVED_PAIRS or independent_clusters < MIN_INDEPENDENT_CLUSTERS:
        return "INCONCLUSIVE_INSUFFICIENT_RESOLUTION"

    if generation_failure_rate > MAX_GENERATION_FAILURE_RATE:
        return "INCONCLUSIVE_TECHNICAL_FAILURE_RATE"

    if tail_breach:
        if mean_delta <= SMALL_MEAN_ADVANTAGE_NATS:
            return "NEGATIVE_TAIL_RISK"
        return "INCONCLUSIVE_TAIL_RISK"

    if mean_delta > 0 and probability_gt_zero >= 0.90:
        return "STRONG_POSITIVE_SIGNAL"
    if mean_delta > 0 and probability_gt_zero >= 0.75:
        return "PROMISING_SIGNAL"
    if mean_delta < 0 and probability_gt_zero <= 0.25:
        return "NEGATIVE_SIGNAL"
    return "INCONCLUSIVE"


def analyze_pairs(
    pairs: list[PairScore],
    *,
    eligible_pair_count: int,
    generation_failure_count: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if eligible_pair_count <= 0:
        raise ValueError("eligible_pair_count must be positive")
    if generation_failure_count < 0 or generation_failure_count > eligible_pair_count:
        raise ValueError("invalid generation_failure_count")
    if not pairs:
        raise ValueError("no resolved scored pairs")

    deltas = [p.delta_log_score for p in pairs]
    clusters = sorted({p.cluster_id for p in pairs})
    bootstrap = cluster_bootstrap_mean_delta(pairs, resamples=resamples, seed=seed)

    mean_delta = float(np.mean(deltas))
    median_delta = float(np.median(deltas))
    p_gt_zero = float(np.mean(np.asarray(bootstrap) > 0.0))
    generation_failure_rate = generation_failure_count / eligible_pair_count

    wins = sum(d > TIE_TOLERANCE_NATS for d in deltas)
    losses = sum(d < -TIE_TOLERANCE_NATS for d in deltas)
    ties = len(deltas) - wins - losses

    tail = _tail_metrics(deltas)

    binary_pairs = [p for p in pairs if p.question_type == "binary"]
    binary_brier = None
    if binary_pairs:
        scope = [p.binary_brier_scope for p in binary_pairs if p.binary_brier_scope is not None]
        control = [p.binary_brier_control for p in binary_pairs if p.binary_brier_control is not None]
        binary_brier = {
            "n": len(scope),
            "scope_mean_brier": float(np.mean(scope)),
            "control_mean_brier": float(np.mean(control)),
            "delta_brier_scope_minus_control": float(np.mean(scope) - np.mean(control)),
        }

    classification = _classification(
        mean_delta=mean_delta,
        probability_gt_zero=p_gt_zero,
        generation_failure_rate=generation_failure_rate,
        resolved_pairs=len(pairs),
        independent_clusters=len(clusters),
        tail_breach=bool(tail["tail_safety_breach"]),
    )

    return {
        "analysis_schema": "1.0",
        "primary_estimand": "mean paired log-score difference in natural-log units (SCOPE minus control)",
        "higher_is_better": True,
        "resolved_pair_count": len(pairs),
        "independent_cluster_count": len(clusters),
        "eligible_pair_count": eligible_pair_count,
        "generation_failure_count": generation_failure_count,
        "generation_failure_rate": generation_failure_rate,
        "mean_delta_nats": mean_delta,
        "median_delta_nats": median_delta,
        "mean_likelihood_ratio_scope_over_control": float(math.exp(mean_delta)),
        "bootstrap": {
            "method": "cluster bootstrap over independent parent/question-group clusters",
            "resamples": resamples,
            "seed": seed,
            "p_mean_delta_gt_zero": p_gt_zero,
            "interval_80_nats": [_quantile(bootstrap, 0.10), _quantile(bootstrap, 0.90)],
            "interval_95_nats": [_quantile(bootstrap, 0.025), _quantile(bootstrap, 0.975)],
        },
        "win_tie_loss": {
            "scope_wins": wins,
            "ties": ties,
            "scope_losses": losses,
            "scope_win_rate": wins / len(pairs),
        },
        "tail": tail,
        "binary_brier_secondary": binary_brier,
        "interpretation_class": classification,
        "thresholds": {
            "minimum_resolved_pairs": MIN_RESOLVED_PAIRS,
            "minimum_independent_clusters": MIN_INDEPENDENT_CLUSTERS,
            "maximum_generation_failure_rate": MAX_GENERATION_FAILURE_RATE,
            "strong_positive_p_gt_zero": 0.90,
            "promising_p_gt_zero": 0.75,
            "negative_p_gt_zero": 0.25,
            "catastrophic_relative_delta_nats": CATASTROPHIC_DELTA_NATS,
            "tail_rate_tolerance": TAIL_RATE_TOLERANCE,
            "small_mean_advantage_nats": SMALL_MEAN_ADVANTAGE_NATS,
        },
        "pair_scores": [asdict(pair) for pair in pairs],
    }
