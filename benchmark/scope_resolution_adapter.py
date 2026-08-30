from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scope_scoring import OUTCOME_ABOVE, OUTCOME_BELOW


CANCELED_RESOLUTIONS = {"annulled", "ambiguous"}
SUPPORTED_TYPES = {
    "BinaryQuestion": "binary",
    "MultipleChoiceQuestion": "multiple_choice",
    "NumericQuestion": "numeric",
    "DiscreteQuestion": "discrete",
    "DateQuestion": "date",
}


@dataclass(frozen=True)
class AdapterResult:
    status: str
    score_record: dict[str, Any] | None
    exclusion: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _normalize_resolution(question_type: str, value: Any) -> Any:
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in CANCELED_RESOLUTIONS:
            return lower
        if lower == OUTCOME_ABOVE:
            return OUTCOME_ABOVE
        if lower == OUTCOME_BELOW:
            return OUTCOME_BELOW

    if question_type == "binary":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"yes", "true"}:
            return True
        if isinstance(value, str) and value.strip().lower() in {"no", "false"}:
            return False
        raise ValueError(f"invalid binary resolution {value!r}")

    if question_type == "multiple_choice":
        _require(
            isinstance(value, str) and value.strip() != "",
            "MC resolution must be a nonempty string",
        )
        return value

    if question_type in {"numeric", "discrete"}:
        if isinstance(value, str) and value in {OUTCOME_ABOVE, OUTCOME_BELOW}:
            return value
        return float(value)

    if question_type == "date":
        if isinstance(value, str) and value in {OUTCOME_ABOVE, OUTCOME_BELOW}:
            return value
        _require(
            isinstance(value, str) and value.strip() != "",
            "date resolution must be ISO text or an out-of-bound marker",
        )
        return value

    raise ValueError(f"unsupported question type {question_type}")


def _resolution_provenance(resolution_record: dict[str, Any]) -> tuple[str, str]:
    source_sha256 = resolution_record.get("source_sha256")
    captured_at_utc = resolution_record.get("captured_at_utc")
    _require(source_sha256 not in (None, ""), "resolution record missing provenance source_sha256")
    _require(captured_at_utc not in (None, ""), "resolution record missing captured_at_utc")
    return str(source_sha256), str(captured_at_utc)


def adapt_pair_to_resolution(
    forecast_record: dict[str, Any],
    resolution_record: dict[str, Any],
) -> AdapterResult:
    """Join one immutable paired forecast record to one resolution record.

    The join key is the immutable Metaculus question/subquestion ID, never the
    display URL or post ID. Group/post ID is retained only as the uncertainty
    cluster key. Resolution provenance is required even for exclusions so that
    every scoring decision remains reconstructable.
    """
    question_id = str(forecast_record.get("question_id", ""))
    _require(question_id != "", "forecast record missing question_id")
    _require(
        str(resolution_record.get("question_id", "")) == question_id,
        "resolution question_id does not match forecast question_id",
    )

    qclass = str(forecast_record.get("question_type", ""))
    _require(qclass in SUPPORTED_TYPES, f"unsupported frozen forecast type {qclass}")
    question_type = SUPPORTED_TYPES[qclass]

    _require(
        forecast_record.get("cluster_id") not in (None, ""),
        "forecast record missing cluster_id",
    )
    _require(
        forecast_record.get("question_snapshot_sha256") not in (None, ""),
        "forecast record missing immutable question snapshot hash",
    )

    source_sha256, captured_at_utc = _resolution_provenance(resolution_record)

    platform_state = str(resolution_record.get("state", "")).strip().lower()
    raw_resolution = resolution_record.get("resolution")

    # A non-resolved platform state is an auditable exclusion. Do not try to
    # coerce a missing/partial resolution value first, because that would turn
    # a valid exclusion into an adapter crash.
    if platform_state != "resolved":
        return AdapterResult(
            status="EXCLUDED",
            score_record=None,
            exclusion={
                "question_id": question_id,
                "cluster_id": str(forecast_record["cluster_id"]),
                "question_type": question_type,
                "reason_code": "ANNULLED_OR_NONRESOLVED_BY_PLATFORM",
                "platform_state": platform_state,
                "resolution": raw_resolution,
                "resolution_source_sha256": source_sha256,
                "resolution_captured_at_utc": captured_at_utc,
            },
        )

    normalized = _normalize_resolution(question_type, raw_resolution)
    if normalized in CANCELED_RESOLUTIONS:
        return AdapterResult(
            status="EXCLUDED",
            score_record=None,
            exclusion={
                "question_id": question_id,
                "cluster_id": str(forecast_record["cluster_id"]),
                "question_type": question_type,
                "reason_code": "ANNULLED_OR_NONRESOLVED_BY_PLATFORM",
                "platform_state": platform_state,
                "resolution": normalized,
                "resolution_source_sha256": source_sha256,
                "resolution_captured_at_utc": captured_at_utc,
            },
        )

    for arm in ("scope", "control"):
        result = forecast_record.get(arm, {}).get("result", {})
        _require(
            result.get("kind") == "forecast_report",
            f"{arm} did not produce a forecast report",
        )
        _require("prediction" in result, f"{arm} forecast is missing prediction")
        _require(
            result.get("prediction_sha256") not in (None, ""),
            f"{arm} forecast is missing prediction hash",
        )

    forecast_id = forecast_record.get("forecast_id") or forecast_record.get("record_sha256")
    _require(forecast_id not in (None, ""), "forecast record missing forecast_id/record_sha256")

    score_record = {
        "forecast_id": str(forecast_id),
        "question_id": question_id,
        "post_id": str(forecast_record.get("post_id", "")),
        "cluster_id": str(forecast_record["cluster_id"]),
        "question_type": question_type,
        "resolution": normalized,
        "scope_prediction": forecast_record["scope"]["result"]["prediction"],
        "control_prediction": forecast_record["control"]["result"]["prediction"],
        "question_snapshot_sha256": str(forecast_record["question_snapshot_sha256"]),
        "scope_prediction_sha256": str(
            forecast_record["scope"]["result"]["prediction_sha256"]
        ),
        "control_prediction_sha256": str(
            forecast_record["control"]["result"]["prediction_sha256"]
        ),
        "resolution_source_sha256": source_sha256,
        "resolution_captured_at_utc": captured_at_utc,
    }
    return AdapterResult(
        status="SCORED_ELIGIBLE",
        score_record=score_record,
        exclusion=None,
    )
